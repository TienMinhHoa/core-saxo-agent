from __future__ import annotations

import asyncio
import hashlib

import pytest

from saxophone.ingestion.models import ChunkIndexRecord
from saxophone.ingestion.vector_state import (
    SqliteVectorIndexStateRepository,
    VectorIndexState,
    build_stale_delete_events,
    reconcile_vector_states,
)
from saxophone.ingestion.vector_sync import VectorSyncService
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository, VectorOutboxEvent


def _state(
    entity_key: str,
    *,
    index_version: str = "index-v1",
    document_ref: str = "doc-1",
    source_version: str = "source-v1",
) -> VectorIndexState:
    return VectorIndexState(
        entity_type="chunk",
        entity_key=entity_key,
        collection_name="document_chunks",
        chroma_record_id=entity_key,
        embedding_input_hash=hashlib.sha256(entity_key.encode("utf-8")).hexdigest(),
        embedding_model="embed-v1",
        embedding_dimensions=2,
        index_version=index_version,
        document_ref=document_ref,
        source_version=source_version,
    )


def test_stale_delete_events_are_deterministic_and_target_exact_state() -> None:
    reconciliation = reconcile_vector_states(
        (_state("chunk-a"), _state("chunk-stale")),
        (_state("chunk-a"),),
    )

    events = build_stale_delete_events(
        reconciliation,
        ingestion_run_id="run-2",
        document_ref="doc-1",
        source_version="source-v2",
    )

    assert events == build_stale_delete_events(
        reconciliation,
        ingestion_run_id="run-2",
        document_ref="doc-1",
        source_version="source-v2",
    )
    assert events[0] == VectorOutboxEvent(
        event_id=events[0].event_id,
        ingestion_run_id="run-2",
        document_ref="doc-1",
        source_version="source-v1",
        collection="document_chunks",
        record_id="chunk-stale",
        operation="delete",
        payload_json="{}",
        index_version="index-v1",
    )


def test_stale_delete_events_are_idempotent_in_sqlite_outbox(tmp_path) -> None:
    repository = SqliteVectorOutboxRepository(tmp_path / "outbox.sqlite")
    reconciliation = reconcile_vector_states((_state("chunk-stale"),), ())
    events = build_stale_delete_events(
        reconciliation,
        ingestion_run_id="run-2",
        document_ref="doc-1",
        source_version="source-v2",
    )

    asyncio.run(repository.enqueue(events))
    asyncio.run(repository.enqueue(events))

    assert asyncio.run(repository.list_pending()) == events


@pytest.mark.anyio
async def test_stale_delete_sync_removes_only_matching_index_version(tmp_path) -> None:
    state_repository = SqliteVectorIndexStateRepository(tmp_path / "state.sqlite")
    stale = _state("chunk-1", index_version="index-v1")
    current = _state("chunk-1", index_version="index-v2")
    await state_repository.mark_synced(stale)
    stored_current = await state_repository.mark_synced(current)

    outbox = SqliteVectorOutboxRepository(tmp_path / "outbox.sqlite")
    await outbox.enqueue(
        (
            VectorOutboxEvent(
                event_id="delete-index-v1",
                ingestion_run_id="run-2",
                document_ref="doc-1",
                source_version="source-v2",
                collection="document_chunks",
                record_id="chunk-1",
                operation="delete",
                payload_json="{}",
                index_version="index-v1",
            ),
        )
    )

    class FakeIndex:
        async def upsert_chunks(self, records: tuple[ChunkIndexRecord, ...]) -> None:
            raise AssertionError("upsert was not expected")

        async def delete_chunks(self, chunk_ids: tuple[str, ...]) -> None:
            assert chunk_ids == ("chunk-1",)

    result = await VectorSyncService(outbox, FakeIndex(), state=state_repository).sync_pending()

    assert result == {"succeeded": 1, "failed": 0}
    assert await state_repository.list_synced(
        entity_type="chunk",
        collection_name="document_chunks",
        index_version="index-v1",
        document_ref="doc-1",
    ) == ()
    assert await state_repository.list_synced(
        entity_type="chunk",
        collection_name="document_chunks",
        index_version="index-v2",
        document_ref="doc-1",
    ) == (stored_current,)


def test_stale_delete_events_require_valid_reconciliation_and_scope() -> None:
    with pytest.raises(TypeError, match="reconciliation"):
        build_stale_delete_events(  # type: ignore[arg-type]
            object(),
            ingestion_run_id="run-2",
            document_ref="doc-1",
            source_version="source-v2",
        )

    reconciliation = reconcile_vector_states((_state("chunk-stale"),), ())
    with pytest.raises(ValueError, match="ingestion_run_id"):
        build_stale_delete_events(
            reconciliation,
            ingestion_run_id=" ",
            document_ref="doc-1",
            source_version="source-v2",
        )
