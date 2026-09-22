from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json

import pytest

from saxophone.ingestion.models import ChunkIndexRecord
from saxophone.ingestion.vector_state import (
    SqliteVectorIndexStateRepository,
    VectorIndexState,
    VectorStateReconciliation,
    reconcile_vector_states,
)
from saxophone.ingestion.vector_sync import VectorSyncService
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository, VectorOutboxEvent


def _state(
    entity_key: str,
    *,
    collection_name: str = "document_chunks",
    document_ref: str = "doc-1",
    source_version: str = "source-v1",
    search_text: str | None = None,
    index_version: str = "index-v1",
) -> VectorIndexState:
    value = search_text or entity_key
    return VectorIndexState(
        entity_type="chunk",
        entity_key=entity_key,
        collection_name=collection_name,
        chroma_record_id=entity_key,
        embedding_input_hash=hashlib.sha256(value.encode("utf-8")).hexdigest(),
        embedding_model="embed-v1",
        embedding_dimensions=2,
        index_version=index_version,
        document_ref=document_ref,
        source_version=source_version,
    )


def test_reconcile_vector_states_separates_unchanged_changed_new_and_stale() -> None:
    existing = (
        _state("chunk-a", search_text="same"),
        _state("chunk-b"),
        _state("chunk-c", search_text="old"),
    )
    desired = (
        _state("chunk-a", search_text="same"),
        _state("chunk-c", search_text="new"),
        _state("chunk-d"),
    )

    result = reconcile_vector_states(existing, desired)

    assert isinstance(result, VectorStateReconciliation)
    assert tuple(item.entity_key for item in result.unchanged) == ("chunk-a",)
    assert tuple(item.entity_key for item in result.changed) == ("chunk-c",)
    assert tuple(item.entity_key for item in result.new) == ("chunk-d",)
    assert tuple(item.chroma_record_id for item in result.stale) == ("chunk-b",)
    assert tuple(item.entity_key for item in result.upsert_required) == ("chunk-c", "chunk-d")


def test_reconcile_vector_states_rejects_cross_scope_and_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="same vector scope"):
        reconcile_vector_states(
            (_state("chunk-a"),),
            (_state("chunk-b", collection_name="other"),),
        )

    duplicate = _state("chunk-a")
    with pytest.raises(ValueError, match="unique entity_key"):
        reconcile_vector_states((duplicate,), (duplicate, duplicate))


def test_reconcile_vector_states_rejects_invalid_state_status() -> None:
    with pytest.raises(ValueError, match="sync_status"):
        VectorIndexState(
            entity_type="chunk",
            entity_key="chunk-a",
            collection_name="document_chunks",
            chroma_record_id="chunk-a",
            embedding_input_hash=hashlib.sha256(b"a").hexdigest(),
            embedding_model="embed-v1",
            embedding_dimensions=2,
            index_version="index-v1",
            sync_status="unknown",  # type: ignore[arg-type]
        )


def test_reconcile_concept_states_use_global_catalog_scope() -> None:
    existing = replace(
        _state("concept-a", collection_name="concept_catalog"),
        entity_type="concept",
        document_ref="catalog-a",
    )
    desired = replace(existing, document_ref="catalog-b")

    result = reconcile_vector_states((existing,), (desired,))

    assert tuple(item.entity_key for item in result.unchanged) == ("concept-a",)


def test_sqlite_vector_index_state_round_trip_and_exact_removal(tmp_path) -> None:
    clock_value = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    repository = SqliteVectorIndexStateRepository(
        tmp_path / "vector-state.sqlite",
        clock=lambda: clock_value,
    )
    state = _state("chunk-a")

    stored = asyncio.run(repository.mark_synced(state))
    assert stored.sync_status.value == "synced"
    assert stored.last_synced_at == clock_value.isoformat(timespec="microseconds")
    assert asyncio.run(repository.list_synced(
        entity_type="chunk",
        collection_name="document_chunks",
        index_version="index-v1",
        document_ref="doc-1",
    )) == (stored,)

    asyncio.run(repository.mark_synced(state))
    with pytest.raises(ValueError, match="different identity"):
        asyncio.run(repository.mark_synced(replace(state, chroma_record_id="other")))

    asyncio.run(repository.remove_record(
        collection_name="document_chunks",
        chroma_record_id="chunk-a",
        document_ref="doc-1",
    ))
    assert asyncio.run(repository.list_synced(
        entity_type="chunk",
        collection_name="document_chunks",
        index_version="index-v1",
        document_ref="doc-1",
    )) == ()


@pytest.mark.anyio
async def test_vector_sync_persists_state_after_upsert_and_removes_it_after_delete(tmp_path) -> None:
    outbox = SqliteVectorOutboxRepository(tmp_path / "outbox.sqlite")
    state_repository = SqliteVectorIndexStateRepository(tmp_path / "vector-state.sqlite")
    record = ChunkIndexRecord(
        chunk_id="chunk-a",
        document_ref="doc-1",
        source_version="source-v1",
        search_text="A source chunk",
        embedding=(0.1, 0.2),
        embedding_profile="embed-v1",
        access_scope="tenant-a",
        metadata={"index_version": "index-v1"},
    )
    upsert_payload = {
        "record": {
            "chunk_id": record.chunk_id,
            "document_ref": record.document_ref,
            "source_version": record.source_version,
            "search_text": record.search_text,
            "embedding": list(record.embedding),
            "embedding_profile": record.embedding_profile,
            "access_scope": record.access_scope,
            "metadata": dict(record.metadata),
        }
    }
    await outbox.enqueue((VectorOutboxEvent(
        event_id="upsert-a",
        document_ref="doc-1",
        source_version="source-v1",
        collection="document_chunks",
        record_id="chunk-a",
        operation="upsert",
        payload_json=json.dumps(upsert_payload),
    ),))

    class FakeIndex:
        async def upsert_chunks(self, records):
            self.records = tuple(records)

        async def delete_chunks(self, chunk_ids):
            self.deleted = tuple(chunk_ids)

    index = FakeIndex()
    service = VectorSyncService(outbox, index, state=state_repository)

    assert await service.sync_pending() == {"succeeded": 1, "failed": 0}
    states = await state_repository.list_synced(
        entity_type="chunk",
        collection_name="document_chunks",
        index_version="index-v1",
        document_ref="doc-1",
    )
    assert [item.chroma_record_id for item in states] == ["chunk-a"]

    await outbox.enqueue((VectorOutboxEvent(
        event_id="delete-a",
        document_ref="doc-1",
        source_version="source-v1",
        collection="document_chunks",
        record_id="chunk-a",
        operation="delete",
        payload_json="{}",
    ),))
    assert await service.sync_pending() == {"succeeded": 1, "failed": 0}
    assert await state_repository.list_synced(
        entity_type="chunk",
        collection_name="document_chunks",
        index_version="index-v1",
        document_ref="doc-1",
    ) == ()
