from __future__ import annotations

import math

import pytest

from saxophone.ingestion.models import (
    ChunkIndexRecord,
    EmbeddingRecord,
    IngestionSourceChunk,
    IngestionCommand,
    IngestionReport,
    VectorHit,
)


def test_ingestion_source_chunk_is_a_pre_embedding_contract() -> None:
    chunk = IngestionSourceChunk(
        chunk_id="chunk-1",
        document_ref="document-1",
        source_version="extract-v1",
        search_text="A source paragraph",
        access_scope="private",
        metadata={"page_start": 2, "heading_path": ["Harmony"]},
    )

    assert chunk.chunk_id == "chunk-1"
    assert chunk.search_text == "A source paragraph"
    assert chunk.metadata["page_start"] == 2

    with pytest.raises(TypeError):
        chunk.metadata["page_start"] = 3


@pytest.mark.parametrize(
    "field",
    ["chunk_id", "document_ref", "source_version", "search_text", "access_scope"],
)
def test_ingestion_source_chunk_rejects_blank_identity_fields(field: str) -> None:
    values = {
        "chunk_id": "chunk-1",
        "document_ref": "document-1",
        "source_version": "extract-v1",
        "search_text": "source text",
        "access_scope": "private",
        "metadata": {},
    }
    values[field] = " "

    with pytest.raises(ValueError, match=field):
        IngestionSourceChunk(**values)


def test_ingestion_source_chunk_requires_mapping_metadata() -> None:
    with pytest.raises(ValueError, match="metadata"):
        IngestionSourceChunk(
            chunk_id="chunk-1",
            document_ref="document-1",
            source_version="extract-v1",
            search_text="source text",
            access_scope="private",
            metadata=[],
        )
from saxophone.ingestion.ports import VectorIndex
from saxophone.ingestion.adapters import ChromaVectorIndex


def test_ingestion_command_contains_profiles_and_scope() -> None:
    command = IngestionCommand(
        document_ref="document-1",
        source_version="extract-v1",
        chunking_profile="heading-chunks-v1",
        tagging_profile="topic-tags-v1",
        embedding_profile="embed-v1",
        index_profile="chroma-v1",
        access_scope="private",
    )

    assert command.document_ref == "document-1"
    assert command.index_profile == "chroma-v1"


def test_embedding_record_requires_dimension_and_finite_values() -> None:
    record = EmbeddingRecord(
        chunk_id="chunk-1",
        source_version="extract-v1",
        model_profile="embed-v1",
        vector=(0.1, -0.2),
    )

    assert record.dimension == 2
    assert record.vector == (0.1, -0.2)

    with pytest.raises(ValueError, match="finite"):
        EmbeddingRecord(
            chunk_id="chunk-1",
            source_version="extract-v1",
            model_profile="embed-v1",
            vector=(math.nan,),
        )


def test_embedding_record_rejects_empty_vector() -> None:
    with pytest.raises(ValueError, match="vector"):
        EmbeddingRecord(
            chunk_id="chunk-1",
            source_version="extract-v1",
            model_profile="embed-v1",
            vector=(),
        )


def test_ingestion_report_cannot_mark_partial_index_as_complete() -> None:
    with pytest.raises(ValueError, match="failed_count"):
        IngestionReport(
            document_ref="document-1",
            source_version="extract-v1",
            chunk_count=3,
            paragraph_count=4,
            tagged_paragraph_count=3,
            failed_paragraph_count=1,
            embedded_count=2,
            reused_embedding_count=0,
            skipped_count=0,
            index_version="chroma-v1",
            indexed=True,
            warnings=(),
            errors=(),
        )


def test_ingestion_report_accepts_complete_zero_error_run() -> None:
    report = IngestionReport(
        document_ref="document-1",
        source_version="extract-v1",
        chunk_count=3,
        paragraph_count=4,
        tagged_paragraph_count=4,
        failed_paragraph_count=0,
        embedded_count=3,
        reused_embedding_count=1,
        skipped_count=0,
        index_version="chroma-v1",
        indexed=True,
        warnings=(),
        errors=(),
    )

    assert report.indexed is True
    assert report.reused_embedding_count == 1


def test_chunk_index_record_validates_projection_and_embedding() -> None:
    record = ChunkIndexRecord(
        chunk_id="chunk-1",
        document_ref="document-1",
        source_version="extract-v1",
        search_text="A validated source chunk",
        embedding=(0.1, 0.2),
        embedding_profile="embed-v1",
        access_scope="private",
        metadata={"page_start": 1},
    )

    assert record.dimension == 2
    assert record.metadata["page_start"] == 1

    with pytest.raises(ValueError, match="search_text"):
        ChunkIndexRecord(
            chunk_id="chunk-1",
            document_ref="document-1",
            source_version="extract-v1",
            search_text=" ",
            embedding=(0.1,),
            embedding_profile="embed-v1",
            access_scope="private",
            metadata={},
        )


def test_vector_hit_exposes_distance_and_source_metadata() -> None:
    hit = VectorHit(
        chunk_id="chunk-1",
        document="A validated source chunk",
        metadata={"source_version": "extract-v1"},
        distance=0.25,
    )

    assert hit.chunk_id == "chunk-1"
    assert hit.metadata["source_version"] == "extract-v1"


def test_vector_index_is_async_port() -> None:
    assert hasattr(VectorIndex, "list_chunk_ids")
    assert hasattr(VectorIndex, "upsert_chunks")
    assert hasattr(VectorIndex, "delete_chunks")
    assert hasattr(VectorIndex, "search")


class _FakeChromaCollection:
    def __init__(self) -> None:
        self.upsert_call = None
        self.delete_call = None
        self.get_call = None
        self.query_call = None

    def get(self, **kwargs):
        self.get_call = kwargs
        return {"ids": ["chunk-1", "stale-chunk"]}

    def upsert(self, **kwargs):
        self.upsert_call = kwargs

    def delete(self, **kwargs):
        self.delete_call = kwargs

    def query(self, **kwargs):
        self.query_call = kwargs
        return {
            "ids": [["chunk-1"]],
            "documents": [["source text"]],
            "metadatas": [[{"chunk_id": "chunk-1", "source_version": "extract-v1"}]],
            "distances": [[0.2]],
        }


def _index_record() -> ChunkIndexRecord:
    return ChunkIndexRecord(
        chunk_id="chunk-1",
        document_ref="document-1",
        source_version="extract-v1",
        search_text="source text",
        embedding=(0.1, 0.2),
        embedding_profile="embed-v1",
        access_scope="private",
        metadata={"page_start": 1},
    )


def test_chunk_index_record_rejects_boolean_vector_values() -> None:
    with pytest.raises(ValueError, match="embedding values must be finite numbers"):
        ChunkIndexRecord(
            chunk_id="chunk-1",
            document_ref="document-1",
            source_version="extract-v1",
            search_text="source text",
            embedding=(True, 0.2),
            embedding_profile="embed-v1",
            access_scope="private",
            metadata={},
        )


def test_embedding_record_rejects_boolean_vector_values() -> None:
    with pytest.raises(ValueError, match="vector values must be finite numbers"):
        EmbeddingRecord(
            chunk_id="chunk-1",
            source_version="extract-v1",
            model_profile="embed-v1",
            vector=(True, 0.2),
        )


@pytest.mark.anyio
async def test_chroma_adapter_runs_upsert_delete_and_search_through_async_port() -> None:
    collection = _FakeChromaCollection()
    index = ChromaVectorIndex(collection)

    ids = await index.list_chunk_ids(document_ref="document-1")
    await index.upsert_chunks([_index_record()])
    await index.delete_chunks(["chunk-1"])
    hits = await index.search((0.3, 0.4), filters={"access_scope": "private"}, limit=3)

    assert ids == ("chunk-1", "stale-chunk")
    assert collection.get_call == {"where": {"document_ref": "document-1"}}
    assert collection.upsert_call["ids"] == ["chunk-1"]
    assert collection.upsert_call["metadatas"][0]["chunk_id"] == "chunk-1"
    assert collection.upsert_call["metadatas"][0]["source_version"] == "extract-v1"
    assert collection.delete_call == {"ids": ["chunk-1"]}
    assert collection.query_call["include"] == ["documents", "metadatas", "distances"]
    assert hits[0].distance == 0.2


@pytest.mark.anyio
async def test_chroma_upsert_rejects_duplicate_chunk_ids_before_provider_io() -> None:
    class _CollectionThatMustNotBeCalled:
        def upsert(self, **kwargs):
            raise AssertionError("duplicate IDs reached Chroma")

    index = ChromaVectorIndex(_CollectionThatMustNotBeCalled())
    record = _index_record()

    with pytest.raises(ValueError, match="unique"):
        await index.upsert_chunks([record, record])


@pytest.mark.anyio
async def test_chroma_upsert_rejects_mixed_embedding_dimensions_before_provider_io() -> None:
    class _CollectionThatMustNotBeCalled:
        def upsert(self, **kwargs):
            raise AssertionError("mixed dimensions reached Chroma")

    first = _index_record()
    second = ChunkIndexRecord(
        chunk_id="chunk-2",
        document_ref=first.document_ref,
        source_version=first.source_version,
        search_text=first.search_text,
        embedding=(0.1, 0.2, 0.3),
        embedding_profile=first.embedding_profile,
        access_scope=first.access_scope,
        metadata={},
    )

    with pytest.raises(ValueError, match="shared dimension"):
        await ChromaVectorIndex(_CollectionThatMustNotBeCalled()).upsert_chunks(
            [first, second]
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "metadata",
    [
        {"optional": None},
        {"nested": {"page": 1}},
        {"nested": [["page"]]},
        {"score": float("nan")},
        {"payload": b"binary"},
        {1: "non-string-key"},
    ],
)
async def test_chroma_upsert_rejects_unsupported_metadata_before_provider_io(
    metadata: dict[object, object],
) -> None:
    class _CollectionThatMustNotBeCalled:
        def upsert(self, **kwargs):
            raise AssertionError("invalid metadata reached Chroma")

    index = ChromaVectorIndex(_CollectionThatMustNotBeCalled())
    record = _index_record()
    invalid_record = ChunkIndexRecord(
        chunk_id=record.chunk_id,
        document_ref=record.document_ref,
        source_version=record.source_version,
        search_text=record.search_text,
        embedding=record.embedding,
        embedding_profile=record.embedding_profile,
        access_scope=record.access_scope,
        metadata=metadata,
    )

    with pytest.raises(ValueError, match="metadata"):
        await index.upsert_chunks([invalid_record])


@pytest.mark.anyio
@pytest.mark.parametrize(
    "reserved_key",
    ["chunk_id", "document_ref", "source_version", "embedding_profile", "access_scope"],
)
async def test_chroma_upsert_rejects_metadata_reserved_key_before_provider_io(
    reserved_key: str,
) -> None:
    class _CollectionThatMustNotBeCalled:
        def upsert(self, **kwargs):
            raise AssertionError("reserved metadata reached Chroma")

    index = ChromaVectorIndex(_CollectionThatMustNotBeCalled())
    record = _index_record()
    invalid_record = ChunkIndexRecord(
        chunk_id=record.chunk_id,
        document_ref=record.document_ref,
        source_version=record.source_version,
        search_text=record.search_text,
        embedding=record.embedding,
        embedding_profile=record.embedding_profile,
        access_scope=record.access_scope,
        metadata={reserved_key: "caller-value"},
    )

    with pytest.raises(ValueError, match="reserved"):
        await index.upsert_chunks([invalid_record])


@pytest.mark.anyio
async def test_chroma_upsert_projects_nested_tuple_metadata_without_provider_error() -> None:
    collection = _FakeChromaCollection()
    index = ChromaVectorIndex(collection)
    record = _index_record()
    record = ChunkIndexRecord(
        chunk_id=record.chunk_id,
        document_ref=record.document_ref,
        source_version=record.source_version,
        search_text=record.search_text,
        embedding=record.embedding,
        embedding_profile=record.embedding_profile,
        access_scope=record.access_scope,
        metadata={"tags": ("music", "phrase")},
    )

    await index.upsert_chunks([record])

    assert collection.upsert_call["metadatas"][0]["tags"] == ["music", "phrase"]


@pytest.mark.anyio
async def test_chroma_upsert_rejects_recursive_metadata_before_provider_io() -> None:
    class _CollectionThatMustNotBeCalled:
        def upsert(self, **kwargs):
            raise AssertionError("recursive metadata reached Chroma")

    recursive_tags: list[object] = ["music"]
    recursive_tags.append(recursive_tags)
    record = _index_record()
    recursive_record = ChunkIndexRecord(
        chunk_id=record.chunk_id,
        document_ref=record.document_ref,
        source_version=record.source_version,
        search_text=record.search_text,
        embedding=record.embedding,
        embedding_profile=record.embedding_profile,
        access_scope=record.access_scope,
        metadata={"tags": recursive_tags},
    )

    with pytest.raises(ValueError, match="cycles"):
        await ChromaVectorIndex(_CollectionThatMustNotBeCalled()).upsert_chunks(
            [recursive_record]
        )


@pytest.mark.anyio
async def test_chroma_search_passes_shared_blocking_io_limiter(monkeypatch) -> None:
    collection = _FakeChromaCollection()
    limiter = object()
    index = ChromaVectorIndex(collection, io_limiter=limiter)
    calls = []

    async def run_sync(function, *args, **kwargs):
        calls.append(kwargs)
        return function(*args)

    monkeypatch.setattr(
        "saxophone.ingestion.adapters.anyio.to_thread.run_sync",
        run_sync,
    )

    await index.search((0.3, 0.4), limit=1)

    assert calls[-1]["limiter"] is limiter


@pytest.mark.parametrize("embedding_dimension", [0, -1, True, 1.5, "3"])
def test_chroma_index_rejects_malformed_embedding_dimension(embedding_dimension) -> None:
    with pytest.raises(ValueError, match="embedding_dimension"):
        ChromaVectorIndex(object(), embedding_dimension=embedding_dimension)


@pytest.mark.anyio
@pytest.mark.parametrize("limit", [-1, True, 1.5, "1"])
async def test_chroma_search_rejects_malformed_limit_before_provider_io(limit) -> None:
    class _CollectionThatMustNotBeCalled:
        def query(self, **kwargs):
            raise AssertionError("malformed limit reached Chroma")

    index = ChromaVectorIndex(_CollectionThatMustNotBeCalled())

    with pytest.raises(ValueError, match="limit"):
        await index.search((0.3, 0.4), limit=limit)


@pytest.mark.anyio
@pytest.mark.parametrize("query_vector", [(), (True, 0.4), (0.3, float("nan")), "0.3"])
async def test_chroma_search_rejects_malformed_query_vector_before_provider_io(query_vector) -> None:
    class _CollectionThatMustNotBeCalled:
        def query(self, **kwargs):
            raise AssertionError("malformed query vector reached Chroma")

    index = ChromaVectorIndex(_CollectionThatMustNotBeCalled())

    with pytest.raises(ValueError, match="query_vector"):
        await index.search(query_vector, limit=1)


@pytest.mark.anyio
async def test_chroma_search_rejects_query_dimension_before_provider_io() -> None:
    class _CollectionThatMustNotBeCalled:
        def query(self, **kwargs):
            raise AssertionError("wrong dimension reached Chroma")

    index = ChromaVectorIndex(_CollectionThatMustNotBeCalled(), embedding_dimension=3)

    with pytest.raises(ValueError, match="query vector dimension"):
        await index.search((0.3, 0.4), limit=1)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "filters",
    [
        [],
        {" ": "private"},
        {"access_scope": None},
        {"page_start": [1, 2]},
        {"page_start": {"$gt": 1}},
        {1: "private"},
    ],
)
async def test_chroma_search_rejects_malformed_filters_before_provider_io(filters) -> None:
    class _CollectionThatMustNotBeCalled:
        def query(self, **kwargs):
            raise AssertionError("malformed filters reached Chroma")

    index = ChromaVectorIndex(_CollectionThatMustNotBeCalled())

    with pytest.raises(ValueError, match="filters"):
        await index.search((0.3, 0.4), filters=filters, limit=1)


@pytest.mark.anyio
async def test_chroma_search_preserves_valid_scalar_filters() -> None:
    collection = _FakeChromaCollection()
    index = ChromaVectorIndex(collection)

    await index.search(
        (0.3, 0.4),
        filters={"access_scope": "private", "page_start": 2},
        limit=1,
    )

    assert collection.query_call["where"] == {
        "access_scope": "private",
        "page_start": 2,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "result",
    [
        {"ids": ["chunk-1"]},
        {
            "ids": [["chunk-1"]],
            "documents": [["text"]],
            "metadatas": [[{}]],
        },
        {
            "ids": [["chunk-1"]],
            "documents": [[42]],
            "metadatas": [[{}]],
            "distances": [[0.1]],
        },
        {
            "ids": [["chunk-1"]],
            "documents": [["text"]],
            "metadatas": [["not-metadata"]],
            "distances": [[0.1]],
        },
        {
            "ids": [["chunk-1"]],
            "documents": [["text"]],
            "metadatas": [[{"page": float("nan")}]],
            "distances": [[0.1]],
        },
        {
            "ids": [["chunk-1"]],
            "documents": [["text"]],
            "metadatas": [[{"tags": [["nested"]]}]],
            "distances": [[0.1]],
        },
        {
            "ids": [["chunk-1"]],
            "documents": [["text"]],
            "metadatas": [[{" ": "private"}]],
            "distances": [[0.1]],
        },
        {
            "ids": [["chunk-1"]],
            "documents": [["text"]],
            "metadatas": [[{}]],
            "distances": [[float("nan")]],
        },
    ],
)
async def test_chroma_vector_index_rejects_malformed_search_results(result) -> None:
    class _MalformedCollection:
        def query(self, **kwargs):
            return result

    index = ChromaVectorIndex(_MalformedCollection())

    with pytest.raises(ValueError, match="Chroma result"):
        await index.search((0.3, 0.4), limit=1)


@pytest.mark.anyio
async def test_chroma_vector_index_rejects_duplicate_search_result_ids() -> None:
    class _DuplicateIdCollection:
        def query(self, **kwargs):
            return {
                "ids": [["chunk-1", "chunk-1"]],
                "documents": [["first", "second"]],
                "metadatas": [[{}, {}]],
                "distances": [[0.1, 0.2]],
            }

    index = ChromaVectorIndex(_DuplicateIdCollection())

    with pytest.raises(ValueError, match="unique"):
        await index.search((0.3, 0.4), limit=2)


@pytest.mark.anyio
@pytest.mark.parametrize("metadata", [{"chunk_id": "other-chunk"}, {"chunk_id": " "}])
async def test_chroma_vector_index_rejects_search_metadata_with_wrong_chunk_identity(
    metadata,
) -> None:
    class _MismatchedMetadataCollection:
        def query(self, **kwargs):
            return {
                "ids": [["chunk-1"]],
                "documents": [["text"]],
                "metadatas": [[metadata]],
                "distances": [[0.1]],
            }

    index = ChromaVectorIndex(_MismatchedMetadataCollection())

    with pytest.raises(ValueError, match="chunk_id"):
        await index.search((0.3, 0.4), limit=1)


@pytest.mark.anyio
async def test_chroma_vector_index_rejects_search_metadata_without_chunk_identity() -> None:
    class _MissingChunkIdentityCollection:
        def query(self, **kwargs):
            return {
                "ids": [["chunk-1"]],
                "documents": [["text"]],
                "metadatas": [[{"source_version": "extract-v1"}]],
                "distances": [[0.1]],
            }

    index = ChromaVectorIndex(_MissingChunkIdentityCollection())

    with pytest.raises(ValueError, match="chunk_id"):
        await index.search((0.3, 0.4), limit=1)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "metadata",
    [
        {"chunk_id": "chunk-1", "document_ref": " "},
        {"chunk_id": "chunk-1", "source_version": 42},
        {"chunk_id": "chunk-1", "access_scope": []},
    ],
)
async def test_chroma_vector_index_rejects_invalid_reserved_search_metadata(
    metadata,
) -> None:
    class _InvalidReservedMetadataCollection:
        def query(self, **kwargs):
            return {
                "ids": [["chunk-1"]],
                "documents": [["text"]],
                "metadatas": [[metadata]],
                "distances": [[0.1]],
            }

    index = ChromaVectorIndex(_InvalidReservedMetadataCollection())

    with pytest.raises(ValueError, match="reserved metadata"):
        await index.search((0.3, 0.4), limit=1)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "result",
    [
        {"ids": "chunk-1"},
        {"ids": ["chunk-1", " "]},
        {"ids": ["chunk-1", 42]},
    ],
)
async def test_chroma_list_chunk_ids_rejects_malformed_provider_ids(result) -> None:
    class _MalformedCollection:
        def get(self, **kwargs):
            return result

    index = ChromaVectorIndex(_MalformedCollection())

    with pytest.raises(ValueError, match="Chroma result ids"):
        await index.list_chunk_ids(document_ref="document-1")


@pytest.mark.anyio
async def test_chroma_list_chunk_ids_rejects_duplicate_provider_ids() -> None:
    class _DuplicateIdCollection:
        def get(self, **kwargs):
            return {"ids": ["chunk-1", "chunk-1"]}

    index = ChromaVectorIndex(_DuplicateIdCollection())

    with pytest.raises(ValueError, match="unique"):
        await index.list_chunk_ids(document_ref="document-1")


@pytest.mark.anyio
@pytest.mark.parametrize("document_ref", ["", "   ", 42, None])
async def test_chroma_list_chunk_ids_rejects_invalid_document_ref_before_provider_io(
    document_ref,
) -> None:
    class _CollectionThatMustNotBeCalled:
        def get(self, **kwargs):
            raise AssertionError("invalid document_ref reached Chroma")

    index = ChromaVectorIndex(_CollectionThatMustNotBeCalled())

    with pytest.raises(ValueError, match="document_ref"):
        await index.list_chunk_ids(document_ref=document_ref)


@pytest.mark.anyio
@pytest.mark.parametrize("chunk_ids", ["chunk-1", ("",), ("chunk-1", 42)])
async def test_chroma_delete_rejects_malformed_ids_before_provider_io(chunk_ids) -> None:
    class _CollectionThatMustNotBeCalled:
        def delete(self, **kwargs):
            raise AssertionError("malformed IDs reached Chroma")

    index = ChromaVectorIndex(_CollectionThatMustNotBeCalled())

    with pytest.raises(ValueError, match="chunk_ids"):
        await index.delete_chunks(chunk_ids)


@pytest.mark.anyio
async def test_chroma_delete_rejects_duplicate_ids_before_provider_io() -> None:
    class _CollectionThatMustNotBeCalled:
        def delete(self, **kwargs):
            raise AssertionError("duplicate IDs reached Chroma")

    index = ChromaVectorIndex(_CollectionThatMustNotBeCalled())

    with pytest.raises(ValueError, match="unique"):
        await index.delete_chunks(("chunk-1", "chunk-1"))
