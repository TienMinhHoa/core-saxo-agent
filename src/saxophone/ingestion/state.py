"""SQLite-backed document and ingestion-run lifecycle state."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from saxophone.documents.policies import is_safe_document_reference


class IngestionStatus(StrEnum):
    """Lifecycle states shared by a document and its active ingestion run."""

    PROCESSING = "processing"
    TAGGED_PENDING_VECTOR_SYNC = "tagged_pending_vector_sync"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DocumentState:
    document_ref: str
    source_hash: str
    active_version: str | None
    status: IngestionStatus
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        _validate_document_ref(self.document_ref)
        _require_non_blank("source_hash", self.source_hash)
        _validate_optional_non_blank("active_version", self.active_version)
        _validate_status(self.status)
        _require_non_blank("created_at", self.created_at)
        _require_non_blank("updated_at", self.updated_at)


@dataclass(frozen=True, slots=True)
class IngestionRunState:
    ingestion_run_id: str
    document_ref: str
    source_version: str
    source_hash: str
    status: IngestionStatus
    started_at: str
    completed_at: str | None
    error_code: str | None

    def __post_init__(self) -> None:
        _require_non_blank("ingestion_run_id", self.ingestion_run_id)
        _validate_document_ref(self.document_ref)
        _require_non_blank("source_version", self.source_version)
        _require_non_blank("source_hash", self.source_hash)
        _validate_status(self.status)
        _require_non_blank("started_at", self.started_at)
        _validate_optional_non_blank("completed_at", self.completed_at)
        _validate_optional_non_blank("error_code", self.error_code)


class SqliteIngestionStateRepository:
    """Persist resumable document and ingestion-run lifecycle state.

    The repository owns only lifecycle state. Relation persistence and vector
    outbox work remain separate repositories so providers never run in this
    transaction boundary.
    """

    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(path, Path) or path.name in {"", ".", ".."}:
            raise ValueError("path must name a SQLite database file")
        if path.exists() and path.is_dir():
            raise ValueError("path must be a file")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        self._path = path.absolute()
        self._clock = clock or _utc_now

    async def start_or_resume(
        self,
        *,
        ingestion_run_id: str,
        document_ref: str,
        source_version: str,
        source_hash: str,
    ) -> IngestionRunState:
        _require_non_blank("ingestion_run_id", ingestion_run_id)
        _validate_document_ref(document_ref)
        _require_non_blank("source_version", source_version)
        _require_non_blank("source_hash", source_hash)
        return await asyncio.to_thread(
            self._start_or_resume,
            ingestion_run_id,
            document_ref,
            source_version,
            source_hash,
        )

    async def get_document(self, document_ref: str) -> DocumentState:
        _validate_document_ref(document_ref)
        result = await asyncio.to_thread(self._get_document, document_ref)
        if result is None:
            raise FileNotFoundError(document_ref)
        return result

    async def get_run(self, ingestion_run_id: str) -> IngestionRunState:
        _require_non_blank("ingestion_run_id", ingestion_run_id)
        result = await asyncio.to_thread(self._get_run, ingestion_run_id)
        if result is None:
            raise FileNotFoundError(ingestion_run_id)
        return result

    async def mark_tagged_pending_vector_sync(
        self,
        ingestion_run_id: str,
    ) -> IngestionRunState:
        _require_non_blank("ingestion_run_id", ingestion_run_id)
        return await asyncio.to_thread(
            self._transition,
            ingestion_run_id,
            IngestionStatus.TAGGED_PENDING_VECTOR_SYNC,
            None,
        )

    async def mark_ready(
        self,
        ingestion_run_id: str,
        *,
        pending_event_count: int = 0,
    ) -> IngestionRunState:
        _require_non_negative_int("pending_event_count", pending_event_count)
        if pending_event_count:
            raise ValueError("pending vector events prevent ready status")
        _require_non_blank("ingestion_run_id", ingestion_run_id)
        return await asyncio.to_thread(
            self._transition,
            ingestion_run_id,
            IngestionStatus.READY,
            None,
        )

    async def mark_failed(
        self,
        ingestion_run_id: str,
        *,
        error_code: str,
    ) -> IngestionRunState:
        _require_non_blank("ingestion_run_id", ingestion_run_id)
        _require_non_blank("error_code", error_code)
        return await asyncio.to_thread(
            self._transition,
            ingestion_run_id,
            IngestionStatus.FAILED,
            error_code,
        )

    def _start_or_resume(
        self,
        ingestion_run_id: str,
        document_ref: str,
        source_version: str,
        source_hash: str,
    ) -> IngestionRunState:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            existing = self._fetch_run(connection, ingestion_run_id)
            if existing is not None:
                self._validate_run_identity(
                    existing,
                    document_ref=document_ref,
                    source_version=source_version,
                    source_hash=source_hash,
                )
                if existing.status is IngestionStatus.FAILED:
                    now = self._timestamp()
                    connection.execute(
                        """
                        UPDATE ingestion_runs
                        SET status = ?, completed_at = NULL, error_code = NULL
                        WHERE ingestion_run_id = ?
                        """,
                        (IngestionStatus.PROCESSING.value, ingestion_run_id),
                    )
                    connection.execute(
                        """
                        UPDATE documents
                        SET source_hash = ?, ingestion_status = ?, updated_at = ?
                        WHERE document_ref = ?
                        """,
                        (
                            source_hash,
                            IngestionStatus.PROCESSING.value,
                            now,
                            document_ref,
                        ),
                    )
                    return _require_run(self._fetch_run(connection, ingestion_run_id))
                return existing

            active = connection.execute(
                """
                SELECT ingestion_run_id
                FROM ingestion_runs
                WHERE document_ref = ?
                  AND status IN (?, ?)
                LIMIT 1
                """,
                (
                    document_ref,
                    IngestionStatus.PROCESSING.value,
                    IngestionStatus.TAGGED_PENDING_VECTOR_SYNC.value,
                ),
            ).fetchone()
            if active is not None:
                raise ValueError("document already has an active ingestion run")

            now = self._timestamp()
            document = self._fetch_document(connection, document_ref)
            if document is None:
                connection.execute(
                    """
                    INSERT INTO documents
                        (document_ref, source_hash, active_version, ingestion_status,
                         created_at, updated_at)
                    VALUES (?, ?, NULL, ?, ?, ?)
                    """,
                    (
                        document_ref,
                        source_hash,
                        IngestionStatus.PROCESSING.value,
                        now,
                        now,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE documents
                    SET source_hash = ?, ingestion_status = ?, updated_at = ?
                    WHERE document_ref = ?
                    """,
                    (
                        source_hash,
                        IngestionStatus.PROCESSING.value,
                        now,
                        document_ref,
                    ),
                )
            try:
                connection.execute(
                    """
                    INSERT INTO ingestion_runs
                        (ingestion_run_id, document_ref, source_version, source_hash,
                         status, started_at, completed_at, error_code)
                    VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
                    """,
                    (
                        ingestion_run_id,
                        document_ref,
                        source_version,
                        source_hash,
                        IngestionStatus.PROCESSING.value,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("document already has an active ingestion run") from error
            return _require_run(self._fetch_run(connection, ingestion_run_id))

    def _transition(
        self,
        ingestion_run_id: str,
        target: IngestionStatus,
        error_code: str | None,
    ) -> IngestionRunState:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            current = self._fetch_run(connection, ingestion_run_id)
            if current is None:
                raise FileNotFoundError(ingestion_run_id)
            if current.status is target:
                return current
            if (
                target is IngestionStatus.READY
                and current.status is not IngestionStatus.TAGGED_PENDING_VECTOR_SYNC
            ):
                raise ValueError("run must be tagged_pending_vector_sync before ready")
            if not _is_allowed_transition(current.status, target):
                raise ValueError(
                    f"cannot transition {current.status.value} to {target.value}"
                )
            now = self._timestamp()
            completed_at = now if target in {
                IngestionStatus.READY,
                IngestionStatus.FAILED,
            } else None
            persisted_error = error_code if target is IngestionStatus.FAILED else None
            connection.execute(
                """
                UPDATE ingestion_runs
                SET status = ?, completed_at = ?, error_code = ?
                WHERE ingestion_run_id = ?
                """,
                (target.value, completed_at, persisted_error, ingestion_run_id),
            )
            if target is IngestionStatus.READY:
                connection.execute(
                    """
                    UPDATE documents
                    SET active_version = ?, ingestion_status = ?, updated_at = ?
                    WHERE document_ref = ?
                    """,
                    (
                        current.source_version,
                        target.value,
                        now,
                        current.document_ref,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE documents
                    SET ingestion_status = ?, updated_at = ?
                    WHERE document_ref = ?
                    """,
                    (target.value, now, current.document_ref),
                )
            return _require_run(self._fetch_run(connection, ingestion_run_id))

    def _get_document(self, document_ref: str) -> DocumentState | None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            return self._fetch_document(connection, document_ref)

    def _get_run(self, ingestion_run_id: str) -> IngestionRunState | None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            return self._fetch_run(connection, ingestion_run_id)

    def _timestamp(self) -> str:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock must return datetime")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds")

    @staticmethod
    def _validate_run_identity(
        run: IngestionRunState,
        *,
        document_ref: str,
        source_version: str,
        source_hash: str,
    ) -> None:
        if (
            run.document_ref != document_ref
            or run.source_version != source_version
            or run.source_hash != source_hash
        ):
            raise ValueError("ingestion run already exists with a different identity")

    @staticmethod
    def _fetch_document(
        connection: sqlite3.Connection,
        document_ref: str,
    ) -> DocumentState | None:
        row = connection.execute(
            """
            SELECT document_ref, source_hash, active_version, ingestion_status,
                   created_at, updated_at
            FROM documents
            WHERE document_ref = ?
            """,
            (document_ref,),
        ).fetchone()
        if row is None:
            return None
        return DocumentState(
            document_ref=row[0],
            source_hash=row[1],
            active_version=row[2],
            status=IngestionStatus(row[3]),
            created_at=row[4],
            updated_at=row[5],
        )

    @staticmethod
    def _fetch_run(
        connection: sqlite3.Connection,
        ingestion_run_id: str,
    ) -> IngestionRunState | None:
        row = connection.execute(
            """
            SELECT ingestion_run_id, document_ref, source_version, source_hash,
                   status, started_at, completed_at, error_code
            FROM ingestion_runs
            WHERE ingestion_run_id = ?
            """,
            (ingestion_run_id,),
        ).fetchone()
        if row is None:
            return None
        return IngestionRunState(
            ingestion_run_id=row[0],
            document_ref=row[1],
            source_version=row[2],
            source_hash=row[3],
            status=IngestionStatus(row[4]),
            started_at=row[5],
            completed_at=row[6],
            error_code=row[7],
        )

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                document_ref TEXT PRIMARY KEY,
                source_hash TEXT NOT NULL,
                active_version TEXT,
                ingestion_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ingestion_runs (
                ingestion_run_id TEXT PRIMARY KEY,
                document_ref TEXT NOT NULL,
                source_version TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                error_code TEXT,
                FOREIGN KEY (document_ref) REFERENCES documents(document_ref)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ingestion_runs_document_status
            ON ingestion_runs(document_ref, status)
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_ingestion_runs_one_active_document
            ON ingestion_runs(document_ref)
            WHERE status IN ('processing', 'tagged_pending_vector_sync')
            """
        )


def _is_allowed_transition(
    current: IngestionStatus,
    target: IngestionStatus,
) -> bool:
    return target in {
        IngestionStatus.PROCESSING: {
            IngestionStatus.TAGGED_PENDING_VECTOR_SYNC,
            IngestionStatus.FAILED,
        },
        IngestionStatus.TAGGED_PENDING_VECTOR_SYNC: {
            IngestionStatus.READY,
            IngestionStatus.FAILED,
        },
        IngestionStatus.READY: set(),
        IngestionStatus.FAILED: {
            IngestionStatus.PROCESSING,
        },
    }.get(current, set())


def _validate_status(status: IngestionStatus) -> None:
    if not isinstance(status, IngestionStatus):
        raise ValueError("status must be an IngestionStatus")


def _require_run(run: IngestionRunState | None) -> IngestionRunState:
    if run is None:
        raise RuntimeError("ingestion run disappeared during transaction")
    return run


def _validate_document_ref(document_ref: str) -> None:
    _require_non_blank("document_ref", document_ref)
    if not is_safe_document_reference(document_ref):
        raise ValueError("document_ref must be a safe document reference")


def _validate_optional_non_blank(name: str, value: str | None) -> None:
    if value is not None:
        _require_non_blank(name, value)


def _require_non_blank(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
