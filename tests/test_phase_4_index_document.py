from __future__ import annotations

from dataclasses import replace

import anyio
import pytest

from saxophone.ingestion.models import (
    ChunkIndexRecord,
    EmbeddingRecord,
    IndexInputRecord,
    IngestionCommand,
)
from saxophone.ingestion.adapters import FileEmbeddingReuseStore, InMemoryEmbeddingReuseStore
from saxophone.ingestion.use_cases import IndexDocument


def _command() -> IngestionCommand:
    return IngestionCommand(
        document_ref="doc-1",
        source_version="source-v1",
        chunking_profile="header-v1",
        tagging_profile="tags-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
    )


def _record(
    chunk_id: str = "chunk-1",
    document_ref: str = "doc-1",
    source_version: str = "source-v1",
    embedding_profile: str = "embed-v1",
    access_scope: str = "tenant-a",
) -> IndexInputRecord:
    return IndexInputRecord(
        chunk_id=chunk_id,
        document_ref=document_ref,
        source_version=source_version,
        search_text="A musical phrase",
        embedding_profile=embedding_profile,
        access_scope=access_scope,
        metadata={"tags": ["phrase"]},
    )


class FakeIndex:
    def __init__(self, error: Exception | None = None, existing_ids=()) -> None:
        self.records = None
        self.error = error
        self.existing_ids = tuple(existing_ids)
        self.deleted_ids = ()

    async def list_chunk_ids(self, *, document_ref):
        return self.existing_ids

    async def delete_chunks(self, chunk_ids):
        self.deleted_ids = tuple(chunk_ids)

    async def upsert_chunks(self, records):
        if self.error:
            raise self.error
        self.records = tuple(records)


class FakeEmbeddingProvider:
    def __init__(self, records: tuple[EmbeddingRecord, ...] | None = None, error: Exception | None = None) -> None:
        self.records = records
        self.error = error
        self.calls = []

    async def embed(self, chunks, *, source_version):
        self.calls.append((tuple(chunks), source_version))
        if self.error:
            raise self.error
        assert self.records is not None
        return self.records


def _embedding(*, chunk_id: str = "chunk-1", source_version: str = "source-v1", model_profile: str = "embed-v1", vector: tuple[float, ...] = (0.9, 0.8)) -> EmbeddingRecord:
    return EmbeddingRecord(
        chunk_id=chunk_id,
        source_version=source_version,
        model_profile=model_profile,
        vector=vector,
    )


@pytest.mark.anyio
async def test_index_document_publishes_records_and_report() -> None:
    index = FakeIndex()
    provider = FakeEmbeddingProvider((_embedding(),))

    report = await IndexDocument(index, provider).execute(_command(), [_record()])

    assert provider.calls == [((("chunk-1", "A musical phrase"),), "source-v1")]
    assert index.records[0].embedding == (0.9, 0.8)
    assert report.indexed is True
    assert report.chunk_count == 1
    assert report.tagged_paragraph_count == 1
    assert report.errors == ()


@pytest.mark.anyio
async def test_index_document_rejects_empty_projection_before_embedding_or_indexing() -> None:
    index = FakeIndex()
    provider = FakeEmbeddingProvider(error=AssertionError("empty projection must not embed"))

    report = await IndexDocument(index, provider).execute(_command(), [])

    assert report.indexed is False
    assert report.chunk_count == 0
    assert report.failed_paragraph_count == 0
    assert report.errors == ("cannot index an empty projection",)
    assert provider.calls == []
    assert index.records is None


@pytest.mark.anyio
async def test_index_document_reconciles_stale_chunks_for_document() -> None:
    index = FakeIndex(existing_ids=("chunk-1", "stale-chunk"))
    provider = FakeEmbeddingProvider((_embedding(),))

    report = await IndexDocument(index, provider).execute(_command(), [_record()])

    assert report.indexed is True
    assert index.deleted_ids == ("stale-chunk",)


@pytest.mark.anyio
async def test_index_document_reports_partial_failure_without_claiming_indexed() -> None:
    index = FakeIndex(RuntimeError("vector store unavailable"), existing_ids=("stale-chunk",))
    provider = FakeEmbeddingProvider((_embedding(),))

    report = await IndexDocument(index, provider).execute(_command(), [_record()])

    assert report.indexed is False
    assert report.failed_paragraph_count == 1
    assert report.errors == ("vector store unavailable",)
    assert index.deleted_ids == ()


@pytest.mark.anyio
async def test_index_document_rejects_cross_document_records_before_index_call() -> None:
    index = FakeIndex()
    provider = FakeEmbeddingProvider((_embedding(),))

    with pytest.raises(ValueError, match="document"):
        await IndexDocument(index, provider).execute(_command(), [_record(document_ref="other")])

    assert index.records is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("embedding_profile", "embed-v2", "embedding profile"),
        ("access_scope", "tenant-b", "access scope"),
    ],
)
async def test_index_document_rejects_records_with_incompatible_index_context(
    field: str, value: str, message: str
) -> None:
    index = FakeIndex()
    provider = FakeEmbeddingProvider((_embedding(),))

    with pytest.raises(ValueError, match=message):
        await IndexDocument(index, provider).execute(_command(), [_record(**{field: value})])

    assert index.records is None


@pytest.mark.anyio
async def test_index_document_reports_embedding_failure_without_index_call() -> None:
    index = FakeIndex()
    provider = FakeEmbeddingProvider(error=RuntimeError("embedding service unavailable"))

    report = await IndexDocument(index, provider).execute(_command(), [_record()])

    assert report.indexed is False
    assert report.embedded_count == 0
    assert report.errors == ("embedding service unavailable",)
    assert index.records is None


@pytest.mark.anyio
async def test_index_document_rejects_inconsistent_embedding_dimensions() -> None:
    index = FakeIndex()
    provider = FakeEmbeddingProvider(
        (
            _embedding(chunk_id="chunk-1", vector=(0.9, 0.8)),
            _embedding(chunk_id="chunk-2", vector=(0.1, 0.2, 0.3)),
        )
    )

    report = await IndexDocument(index, provider).execute(
        _command(), [_record(), _record(chunk_id="chunk-2")]
    )

    assert report.indexed is False
    assert report.errors == ("embedding dimensions must match",)
    assert index.records is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "embedding",
    [_embedding(source_version="other"), _embedding(model_profile="embed-v2"), _embedding(chunk_id="other")],
)
async def test_index_document_rejects_embedding_scope_before_index_call(embedding: EmbeddingRecord) -> None:
    index = FakeIndex()
    provider = FakeEmbeddingProvider((embedding,))

    report = await IndexDocument(index, provider).execute(_command(), [_record()])

    assert report.indexed is False
    assert report.embedded_count == 0
    assert index.records is None


@pytest.mark.anyio
async def test_index_document_reuses_unchanged_embedding_without_calling_provider() -> None:
    index = FakeIndex()
    provider = FakeEmbeddingProvider(error=AssertionError("unchanged record must not be embedded"))
    reuse_store = InMemoryEmbeddingReuseStore()
    cached = await IndexDocument(index, FakeEmbeddingProvider((_embedding(),)), reuse_store).execute(
        _command(), [_record()]
    )
    assert cached.indexed is True

    report = await IndexDocument(index, provider, reuse_store).execute(_command(), [_record()])

    assert report.indexed is True
    assert report.embedded_count == 0
    assert report.reused_embedding_count == 1
    assert provider.calls == []


@pytest.mark.anyio
async def test_index_document_reembeds_when_source_text_changes() -> None:
    index = FakeIndex()
    first_provider = FakeEmbeddingProvider((_embedding(vector=(0.9, 0.8)),))
    reuse_store = InMemoryEmbeddingReuseStore()
    await IndexDocument(index, first_provider, reuse_store).execute(_command(), [_record()])

    changed = IndexInputRecord(
        chunk_id="chunk-1",
        document_ref="doc-1",
        source_version="source-v1",
        search_text="A changed musical phrase",
        embedding_profile="embed-v1",
        access_scope="tenant-a",
        metadata={"tags": ["phrase"]},
    )
    second_provider = FakeEmbeddingProvider((_embedding(vector=(0.1, 0.2)),))

    report = await IndexDocument(index, second_provider, reuse_store).execute(_command(), [changed])

    assert report.reused_embedding_count == 0
    assert second_provider.calls == [((('chunk-1', 'A changed musical phrase'),), "source-v1")]


@pytest.mark.anyio
async def test_file_embedding_reuse_store_survives_new_instance(tmp_path) -> None:
    path = tmp_path / "embedding-reuse.json"
    first_store = FileEmbeddingReuseStore(path)
    first_provider = FakeEmbeddingProvider((_embedding(),))

    first = await IndexDocument(FakeIndex(), first_provider, first_store).execute(
        _command(), [_record()]
    )

    assert first.indexed is True
    second_store = FileEmbeddingReuseStore(path)
    second_provider = FakeEmbeddingProvider(
        error=AssertionError("restart must reuse persisted embedding")
    )
    second = await IndexDocument(FakeIndex(), second_provider, second_store).execute(
        _command(), [_record()]
    )

    assert second.indexed is True
    assert second.embedded_count == 0
    assert second.reused_embedding_count == 1


@pytest.mark.anyio
async def test_file_embedding_reuse_store_rejects_corrupt_payload(tmp_path) -> None:
    path = tmp_path / "embedding-reuse.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="embedding reuse store"):
        await FileEmbeddingReuseStore(path).find([_record()])


@pytest.mark.anyio
async def test_file_embedding_reuse_store_serializes_concurrent_writers(tmp_path) -> None:
    path = tmp_path / "embedding-reuse.json"
    first = ChunkIndexRecord(
        chunk_id="chunk-1",
        document_ref="doc-1",
        source_version="source-v1",
        search_text="A musical phrase",
        embedding=(0.9, 0.8),
        embedding_profile="embed-v1",
        access_scope="tenant-a",
        metadata={},
    )
    second = replace(first, chunk_id="chunk-2", embedding=(0.1, 0.2))
    first_store = FileEmbeddingReuseStore(path)
    second_store = FileEmbeddingReuseStore(path)

    async def save(store, record) -> None:
        await store.save((record,))

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(save, first_store, first)
        tasks.start_soon(save, second_store, second)

    records = await first_store.find(
        [
            _record(),
            replace(_record(), chunk_id="chunk-2", search_text="A musical phrase"),
        ]
    )
    assert set(records) == {"chunk-1", "chunk-2"}
