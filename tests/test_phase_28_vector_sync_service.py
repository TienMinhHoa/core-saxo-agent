from __future__ import annotations

import json
from pathlib import Path

import pytest

from saxophone.ingestion.models import ChunkIndexRecord
from saxophone.ingestion.vector_sync import VectorSyncService
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository, VectorOutboxEvent


class FakeVectorIndex:
    def __init__(self) -> None:
        self.upserts: list[ChunkIndexRecord] = []
        self.deletes: list[str] = []

    async def upsert_chunks(self, records):
        self.upserts.extend(records)

    async def delete_chunks(self, chunk_ids):
        self.deletes.extend(chunk_ids)


def _record() -> ChunkIndexRecord:
    return ChunkIndexRecord(
        chunk_id="chunk-1", document_ref="doc-1", source_version="v1",
        search_text="text", embedding=(0.1, 0.2), embedding_profile="embed-v1",
        access_scope="tenant-a", metadata={"tags": ["music"]},
    )


def _event(record: ChunkIndexRecord, *, operation: str = "upsert") -> VectorOutboxEvent:
    payload = {"record": {
        "chunk_id": record.chunk_id, "document_ref": record.document_ref,
        "source_version": record.source_version, "search_text": record.search_text,
        "embedding": list(record.embedding), "embedding_profile": record.embedding_profile,
        "access_scope": record.access_scope, "metadata": dict(record.metadata),
    }} if operation == "upsert" else {}
    return VectorOutboxEvent(
        event_id=f"event-{operation}", document_ref=record.document_ref,
        source_version=record.source_version, collection="document_chunks",
        record_id=record.chunk_id, operation=operation,
        payload_json=json.dumps(payload),
    )


@pytest.mark.anyio
async def test_vector_sync_applies_events_and_marks_success(tmp_path: Path) -> None:
    repo = SqliteVectorOutboxRepository(tmp_path / "outbox.sqlite")
    record = _record()
    await repo.enqueue((_event(record), _event(record, operation="delete")))
    index = FakeVectorIndex()

    report = await VectorSyncService(repo, index).sync_pending()

    assert report == {"succeeded": 2, "failed": 0}
    assert index.upserts == [record]
    assert index.deletes == ["chunk-1"]
    assert all(event.status.value == "succeeded" for event in (
        await repo.get("event-upsert"), await repo.get("event-delete")
    ))


@pytest.mark.anyio
async def test_vector_sync_marks_failed_and_continues(tmp_path: Path) -> None:
    repo = SqliteVectorOutboxRepository(tmp_path / "outbox.sqlite")
    record = _record()
    await repo.enqueue((_event(record),))

    class FailingIndex(FakeVectorIndex):
        async def upsert_chunks(self, records):
            raise RuntimeError("chroma unavailable")

    report = await VectorSyncService(repo, FailingIndex()).sync_pending()

    assert report == {"succeeded": 0, "failed": 1}
    event = await repo.get("event-upsert")
    assert event.status.value == "failed"
    assert event.attempts == 1
    assert event.last_error == "chroma unavailable"
