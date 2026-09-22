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
    ingestion_run_id: str | None = None
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
        if self.ingestion_run_id is not None and (
            not isinstance(self.ingestion_run_id, str) or not self.ingestion_run_id.strip()
        ):
            raise ValueError("ingestion_run_id must be blank or null")
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

    async def list_pending(
        self,
        *,
        limit: int = 100,
        ingestion_run_id: str | None = None,
    ) -> tuple[VectorOutboxEvent, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be positive")
        self._validate_ingestion_run_id(ingestion_run_id)
        return await asyncio.to_thread(self._list_pending, limit, ingestion_run_id)

    async def count_pending(self, *, ingestion_run_id: str | None = None) -> int:
        """Count retryable events without consuming them."""
        self._validate_ingestion_run_id(ingestion_run_id)
        return await asyncio.to_thread(self._count_pending, ingestion_run_id)

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
                existing = connection.execute(
                    """
                    SELECT ingestion_run_id, document_ref, source_version, collection,
                           record_id, operation, payload_json
                    FROM vector_outbox
                    WHERE event_id = ?
                    """,
                    (item.event_id,),
                ).fetchone()
                if existing is not None:
                    expected = (
                        item.ingestion_run_id,
                        item.document_ref,
                        item.source_version,
                        item.collection,
                        item.record_id,
                        item.operation,
                        item.payload_json,
                    )
                    if existing != expected:
                        raise ValueError("event_id already exists with different payload or scope")
                    continue
                connection.execute(
                    """
                    INSERT INTO vector_outbox
                        (event_id, ingestion_run_id, document_ref, source_version,
                         collection, record_id, operation, payload_json, status,
                         attempts, last_error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.event_id,
                        item.ingestion_run_id,
                        item.document_ref,
                        item.source_version,
                        item.collection,
                        item.record_id,
                        item.operation,
                        item.payload_json,
                        item.status.value,
                        item.attempts,
                        item.last_error,
                    ),
                )

    def _list_pending(
        self, limit: int, ingestion_run_id: str | None
    ) -> tuple[VectorOutboxEvent, ...]:
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            query = """
                SELECT event_id, document_ref, source_version, collection,
                       record_id, operation, payload_json, ingestion_run_id,
                       status, attempts, last_error
                FROM vector_outbox
                WHERE status IN ('pending', 'failed')
            """
            parameters: tuple[object, ...]
            if ingestion_run_id is None:
                parameters = (limit,)
            else:
                query += " AND ingestion_run_id = ?"
                parameters = (ingestion_run_id, limit)
            query += " ORDER BY event_id LIMIT ?"
            rows = connection.execute(query, parameters).fetchall()
        return tuple(self._event_from_row(row) for row in rows)

    def _count_pending(self, ingestion_run_id: str | None) -> int:
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            query = "SELECT COUNT(*) FROM vector_outbox WHERE status IN ('pending', 'failed')"
            parameters: tuple[object, ...] = ()
            if ingestion_run_id is not None:
                query += " AND ingestion_run_id = ?"
                parameters = (ingestion_run_id,)
            row = connection.execute(query, parameters).fetchone()
        return int(row[0]) if row is not None else 0

    def _get(self, event_id: str) -> VectorOutboxEvent | None:
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            row = connection.execute(
                """
                SELECT event_id, document_ref, source_version, collection,
                       record_id, operation, payload_json, ingestion_run_id,
                       status, attempts, last_error
                FROM vector_outbox
                WHERE event_id = ?
                """,
                (event_id,),
            ).fetchone()
        return None if row is None else self._event_from_row(row)

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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS vector_outbox (
                event_id TEXT PRIMARY KEY,
                ingestion_run_id TEXT,
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
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(vector_outbox)").fetchall()
        }
        if "ingestion_run_id" not in columns:
            connection.execute("ALTER TABLE vector_outbox ADD COLUMN ingestion_run_id TEXT")

    @staticmethod
    def _validate_event_id(event_id: str) -> None:
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id must not be blank")

    @staticmethod
    def _validate_ingestion_run_id(ingestion_run_id: str | None) -> None:
        if ingestion_run_id is not None and (
            not isinstance(ingestion_run_id, str) or not ingestion_run_id.strip()
        ):
            raise ValueError("ingestion_run_id must be blank or null")

    @staticmethod
    def _event_from_row(row: tuple[object, ...]) -> VectorOutboxEvent:
        return VectorOutboxEvent(
            event_id=row[0],
            document_ref=row[1],
            source_version=row[2],
            collection=row[3],
            record_id=row[4],
            operation=row[5],
            payload_json=row[6],
            ingestion_run_id=row[7],
            status=OutboxStatus(row[8]),
            attempts=row[9],
            last_error=row[10],
        )
