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
            "metadatas": [[{"source_version": "extract-v1"}]],
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
    assert collection.upsert_call["metadatas"][0]["source_version"] == "extract-v1"
    assert collection.delete_call == {"ids": ["chunk-1"]}
    assert collection.query_call["include"] == ["documents", "metadatas", "distances"]
    assert hits[0].distance == 0.2


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
