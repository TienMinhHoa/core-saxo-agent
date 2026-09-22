from __future__ import annotations

import asyncio
import json
import sqlite3

import pytest

from saxophone.ingestion.models import ChunkIndexRecord
from saxophone.ingestion.vector_sync import VectorSyncService
from saxophone.tagging.vector_outbox import OutboxStatus, SqliteVectorOutboxRepository, VectorOutboxEvent


def _record(chunk_id: str) -> ChunkIndexRecord:
    return ChunkIndexRecord(
        chunk_id=chunk_id,
        document_ref="doc-1",
        source_version="v1",
        search_text=chunk_id,
        embedding=(0.1, 0.2),
        embedding_profile="embed-v1",
        access_scope="tenant-a",
        metadata={},
    )


def _event(run_id: str, record: ChunkIndexRecord) -> VectorOutboxEvent:
    payload = json.dumps(
        {
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
    )
    return VectorOutboxEvent(
        event_id=f"{run_id}-{record.chunk_id}",
        ingestion_run_id=run_id,
        document_ref=record.document_ref,
        source_version=record.source_version,
        collection="document_chunks",
        record_id=record.chunk_id,
        operation="upsert",
        payload_json=payload,
    )


class _FakeVectorIndex:
    def __init__(self) -> None:
        self.upserts: list[ChunkIndexRecord] = []

    async def upsert_chunks(self, records):
        self.upserts.extend(records)

    async def delete_chunks(self, chunk_ids):
        raise AssertionError("delete was not expected")


@pytest.mark.anyio
async def test_outbox_lists_pending_events_for_one_ingestion_run(tmp_path) -> None:
    repository = SqliteVectorOutboxRepository(tmp_path / "outbox.sqlite")
    first = _event("run-a", _record("chunk-a"))
    second = _event("run-b", _record("chunk-b"))

    await repository.enqueue((first, second))

    assert await repository.list_pending(ingestion_run_id="run-a") == (first,)
    assert await repository.list_pending() == (first, second)


@pytest.mark.anyio
async def test_vector_sync_scopes_processing_to_one_ingestion_run(tmp_path) -> None:
    repository = SqliteVectorOutboxRepository(tmp_path / "outbox.sqlite")
    first = _event("run-a", _record("chunk-a"))
    second = _event("run-b", _record("chunk-b"))
    await repository.enqueue((first, second))
    index = _FakeVectorIndex()

    report = await VectorSyncService(repository, index).sync_pending(
        ingestion_run_id="run-a"
    )

    assert report == {"succeeded": 1, "failed": 0}
    assert index.upserts == [_record("chunk-a")]
    assert (await repository.get(first.event_id)).status is OutboxStatus.SUCCEEDED
    assert (await repository.get(second.event_id)).status is OutboxStatus.PENDING


def test_vector_outbox_rejects_blank_ingestion_run_id() -> None:
    with pytest.raises(ValueError, match="ingestion_run_id"):
        VectorOutboxEvent(
            event_id="event-1",
            ingestion_run_id=" ",
            document_ref="doc-1",
            source_version="v1",
            collection="document_chunks",
            record_id="chunk-1",
            operation="delete",
            payload_json="{}",
        )


def test_vector_outbox_migrates_existing_schema_without_run_identity(tmp_path) -> None:
    database = tmp_path / "outbox.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE vector_outbox (
                event_id TEXT PRIMARY KEY,
                document_ref TEXT NOT NULL,
                source_version TEXT NOT NULL,
                collection TEXT NOT NULL,
                record_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                last_error TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO vector_outbox
                (event_id, document_ref, source_version, collection, record_id,
                 operation, payload_json, status, attempts, last_error)
            VALUES ('legacy', 'doc-1', 'v1', 'document_chunks', 'chunk-legacy',
                    'delete', '{}', 'pending', 0, NULL)
            """
        )

    repository = SqliteVectorOutboxRepository(database)

    loaded = asyncio.run(repository.list_pending())

    assert loaded[0].event_id == "legacy"
    assert loaded[0].ingestion_run_id is None
