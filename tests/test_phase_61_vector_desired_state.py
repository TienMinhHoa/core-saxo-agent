from __future__ import annotations

import hashlib

import pytest

from saxophone.ingestion.models import ChunkIndexRecord
from saxophone.ingestion.vector_state import VectorSyncStatus, build_chunk_vector_states


def _record(
    chunk_id: str = "chunk-1",
    *,
    document_ref: str = "doc-1",
    source_version: str = "source-v1",
    search_text: str = "Major triad.",
    metadata: dict[str, object] | None = None,
) -> ChunkIndexRecord:
    return ChunkIndexRecord(
        chunk_id=chunk_id,
        document_ref=document_ref,
        source_version=source_version,
        search_text=search_text,
        embedding=(0.1, 0.2),
        embedding_profile="embedding-v1",
        access_scope="tenant-a",
        metadata=metadata or {},
    )


def test_build_chunk_vector_states_is_sorted_and_preserves_embedding_identity() -> None:
    states = build_chunk_vector_states(
        (
            _record("chunk-2", search_text="Minor triad."),
            _record("chunk-1"),
        ),
        index_version="index-v2",
    )

    assert [state.entity_key for state in states] == ["chunk-1", "chunk-2"]
    first = states[0]
    assert first.entity_type == "chunk"
    assert first.collection_name == "document_chunks"
    assert first.chroma_record_id == "chunk-1"
    assert first.embedding_input_hash == hashlib.sha256(
        "Major triad.".encode("utf-8")
    ).hexdigest()
    assert first.embedding_model == "embedding-v1"
    assert first.embedding_dimensions == 2
    assert first.index_version == "index-v2"
    assert first.sync_status is VectorSyncStatus.SYNCED
    assert first.document_ref == "doc-1"
    assert first.source_version == "source-v1"


def test_build_chunk_vector_states_requires_one_document_and_source_scope() -> None:
    with pytest.raises(ValueError, match="same document"):
        build_chunk_vector_states(
            (_record(), _record("chunk-2", document_ref="doc-2")),
            index_version="index-v1",
        )

    with pytest.raises(ValueError, match="same source version"):
        build_chunk_vector_states(
            (_record(), _record("chunk-2", source_version="source-v2")),
            index_version="index-v1",
        )


def test_build_chunk_vector_states_rejects_duplicate_ids_and_blank_index_version() -> None:
    with pytest.raises(ValueError, match="unique chunk IDs"):
        build_chunk_vector_states((_record(), _record()), index_version="index-v1")

    with pytest.raises(ValueError, match="index_version"):
        build_chunk_vector_states((_record(),), index_version=" ")
