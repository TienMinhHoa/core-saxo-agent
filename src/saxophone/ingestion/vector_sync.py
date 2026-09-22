"""Application service for draining durable vector outbox events."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Protocol

from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository, VectorOutboxEvent

from .models import ChunkIndexRecord


class _VectorIndex(Protocol):
    async def upsert_chunks(self, records: tuple[ChunkIndexRecord, ...]) -> None: ...

    async def delete_chunks(self, chunk_ids: tuple[str, ...]) -> None: ...


class VectorSyncService:
    """Apply pending/failed events and persist success or retry state per event."""

    def __init__(self, outbox: SqliteVectorOutboxRepository, vector_index: _VectorIndex) -> None:
        if not callable(getattr(outbox, "list_pending", None)):
            raise TypeError("outbox must provide list_pending")
        if not callable(getattr(vector_index, "upsert_chunks", None)):
            raise TypeError("vector_index must provide upsert_chunks")
        if not callable(getattr(vector_index, "delete_chunks", None)):
            raise TypeError("vector_index must provide delete_chunks")
        self._outbox = outbox
        self._vector_index = vector_index

    async def sync_pending(self, *, limit: int = 100) -> dict[str, int]:
        events = await self._outbox.list_pending(limit=limit)
        succeeded = failed = 0
        for event in events:
            try:
                await self._apply(event)
            except Exception as error:
                await self._outbox.mark_failed(event.event_id, str(error) or type(error).__name__)
                failed += 1
            else:
                await self._outbox.mark_succeeded(event.event_id)
                succeeded += 1
        return {"succeeded": succeeded, "failed": failed}

    async def _apply(self, event: VectorOutboxEvent) -> None:
        if event.collection != "document_chunks":
            raise ValueError("unsupported vector collection")
        if event.operation == "delete":
            await self._vector_index.delete_chunks((event.record_id,))
            return
        try:
            payload = json.loads(event.payload_json)
            record_payload = payload["record"]
            if not isinstance(record_payload, Mapping):
                raise ValueError
            record = ChunkIndexRecord(
                chunk_id=record_payload["chunk_id"],
                document_ref=record_payload["document_ref"],
                source_version=record_payload["source_version"],
                search_text=record_payload["search_text"],
                embedding=tuple(record_payload["embedding"]),
                embedding_profile=record_payload["embedding_profile"],
                access_scope=record_payload["access_scope"],
                metadata=record_payload["metadata"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("vector upsert payload is invalid") from error
        if record.chunk_id != event.record_id or record.document_ref != event.document_ref:
            raise ValueError("vector upsert payload identity does not match event")
        await self._vector_index.upsert_chunks((record,))
