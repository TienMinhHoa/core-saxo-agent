"""SQLite-backed idempotent work items for vector synchronization."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from collections.abc import Sequence


class OutboxStatus(StrEnum):
    PENDING = "pending"
    FAILED = "failed"
    SUCCEEDED = "succeeded"


@dataclass(frozen=True, slots=True)
class VectorOutboxEvent:
    event_id: str
    document_ref: str
    source_version: str
    collection: str
    record_id: str
    operation: str
    payload_json: str
    status: OutboxStatus = OutboxStatus.PENDING
    attempts: int = 0
    last_error: str | None = None

    def __post_init__(self) -> None:
        for name in ("event_id", "document_ref", "source_version", "collection", "record_id", "operation", "payload_json"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be blank")
        if self.operation not in {"upsert", "delete"}:
            raise ValueError("operation must be upsert or delete")
        if not isinstance(self.status, OutboxStatus):
            object.__setattr__(self, "status", OutboxStatus(self.status))
        if not isinstance(self.attempts, int) or self.attempts < 0:
            raise ValueError("attempts must not be negative")
        if self.last_error is not None and (not isinstance(self.last_error, str) or not self.last_error.strip()):
            raise ValueError("last_error must be blank or null")


class SqliteVectorOutboxRepository:
    """Persist vector work items without duplicating a stable event ID."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path) or path.name in {"", ".", ".."}:
            raise ValueError("path must name a SQLite database file")
        if path.exists() and path.is_dir():
            raise ValueError("path must be a file")
        self._path = path.absolute()

    async def enqueue(self, events: Sequence[VectorOutboxEvent]) -> None:
        normalized = tuple(events)
        if any(not isinstance(item, VectorOutboxEvent) for item in normalized):
            raise ValueError("events must contain VectorOutboxEvent values")
        await asyncio.to_thread(self._enqueue, normalized)

    async def list_pending(self, *, limit: int = 100) -> tuple[VectorOutboxEvent, ...]:
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be positive")
        return await asyncio.to_thread(self._list_pending, limit)

    async def get(self, event_id: str) -> VectorOutboxEvent:
        self._validate_event_id(event_id)
        result = await asyncio.to_thread(self._get, event_id)
        if result is None:
            raise FileNotFoundError(event_id)
        return result

    async def mark_failed(self, event_id: str, error: str) -> None:
        self._validate_event_id(event_id)
        if not isinstance(error, str) or not error.strip():
            raise ValueError("error must not be blank")
        await asyncio.to_thread(self._transition, event_id, OutboxStatus.FAILED, error)

    async def requeue(self, event_id: str) -> None:
        self._validate_event_id(event_id)
        await asyncio.to_thread(self._transition, event_id, OutboxStatus.PENDING, None)

    async def mark_succeeded(self, event_id: str) -> None:
        self._validate_event_id(event_id)
        await asyncio.to_thread(self._transition, event_id, OutboxStatus.SUCCEEDED, None)

    def _enqueue(self, events: tuple[VectorOutboxEvent, ...]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            for item in events:
                existing = connection.execute("SELECT payload_json FROM vector_outbox WHERE event_id = ?", (item.event_id,)).fetchone()
                if existing is not None:
                    if existing[0] != item.payload_json:
                        raise ValueError("event_id already exists with different payload")
                    continue
                connection.execute(
                    "INSERT INTO vector_outbox (event_id, document_ref, source_version, collection, record_id, operation, payload_json, status, attempts, last_error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (item.event_id, item.document_ref, item.source_version, item.collection, item.record_id, item.operation, item.payload_json, item.status.value, item.attempts, item.last_error),
                )

    def _list_pending(self, limit: int) -> tuple[VectorOutboxEvent, ...]:
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            rows = connection.execute("SELECT event_id, document_ref, source_version, collection, record_id, operation, payload_json, status, attempts, last_error FROM vector_outbox WHERE status IN ('pending', 'failed') ORDER BY event_id LIMIT ?", (limit,)).fetchall()
        return tuple(VectorOutboxEvent(*row[:7], status=OutboxStatus(row[7]), attempts=row[8], last_error=row[9]) for row in rows)

    def _get(self, event_id: str) -> VectorOutboxEvent | None:
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            row = connection.execute("SELECT event_id, document_ref, source_version, collection, record_id, operation, payload_json, status, attempts, last_error FROM vector_outbox WHERE event_id = ?", (event_id,)).fetchone()
        return None if row is None else VectorOutboxEvent(*row[:7], status=OutboxStatus(row[7]), attempts=row[8], last_error=row[9])

    def _transition(self, event_id: str, status: OutboxStatus, error: str | None) -> None:
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            if status is OutboxStatus.FAILED:
                connection.execute("UPDATE vector_outbox SET status = ?, attempts = attempts + 1, last_error = ? WHERE event_id = ?", (status.value, error, event_id))
            else:
                connection.execute("UPDATE vector_outbox SET status = ?, last_error = ? WHERE event_id = ?", (status.value, error, event_id))
            if connection.total_changes == 0:
                raise FileNotFoundError(event_id)

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE IF NOT EXISTS vector_outbox (event_id TEXT PRIMARY KEY, document_ref TEXT NOT NULL, source_version TEXT NOT NULL, collection TEXT NOT NULL, record_id TEXT NOT NULL, operation TEXT NOT NULL, payload_json TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL, last_error TEXT)")

    @staticmethod
    def _validate_event_id(event_id: str) -> None:
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id must not be blank")
