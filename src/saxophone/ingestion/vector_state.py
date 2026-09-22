"""Durable vector-index state and deterministic re-ingestion reconciliation."""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from saxophone.documents.policies import is_safe_document_reference


class VectorSyncStatus(StrEnum):
    """State of one vector record in the configured collection."""

    SYNCED = "synced"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class VectorIndexState:
    """The durable identity and embedding inputs for one indexed entity."""

    entity_type: str
    entity_key: str
    collection_name: str
    chroma_record_id: str
    embedding_input_hash: str
    embedding_model: str
    embedding_dimensions: int
    index_version: str
    sync_status: VectorSyncStatus = VectorSyncStatus.SYNCED
    last_synced_at: str | None = None
    document_ref: str | None = None
    source_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.entity_type, str) or self.entity_type not in {"chunk", "concept"}:
            raise ValueError("entity_type must be chunk or concept")
        for name in (
            "entity_key",
            "collection_name",
            "chroma_record_id",
            "embedding_model",
            "index_version",
        ):
            _require_non_blank(name, getattr(self, name))
        if not _is_sha256(self.embedding_input_hash):
            raise ValueError("embedding_input_hash must be a SHA-256 hex digest")
        if (
            isinstance(self.embedding_dimensions, bool)
            or not isinstance(self.embedding_dimensions, int)
            or self.embedding_dimensions < 1
        ):
            raise ValueError("embedding_dimensions must be a positive integer")
        if not isinstance(self.sync_status, VectorSyncStatus):
            try:
                object.__setattr__(self, "sync_status", VectorSyncStatus(self.sync_status))
            except ValueError as error:
                raise ValueError("sync_status must be synced or stale") from error
        _validate_optional_non_blank("last_synced_at", self.last_synced_at)
        if self.document_ref is not None:
            _require_non_blank("document_ref", self.document_ref)
            if not is_safe_document_reference(self.document_ref):
                raise ValueError("document_ref must be a safe document reference")
        _validate_optional_non_blank("source_version", self.source_version)


@dataclass(frozen=True, slots=True)
class VectorStateReconciliation:
    """Deterministic differences between stored and desired vector state."""

    unchanged: tuple[VectorIndexState, ...]
    changed: tuple[VectorIndexState, ...]
    new: tuple[VectorIndexState, ...]
    stale: tuple[VectorIndexState, ...]

    @property
    def upsert_required(self) -> tuple[VectorIndexState, ...]:
        """Return changed and new records in stable entity-key order."""

        return tuple(sorted((*self.changed, *self.new), key=lambda item: item.entity_key))


def reconcile_vector_states(
    existing: Sequence[VectorIndexState],
    desired: Sequence[VectorIndexState],
) -> VectorStateReconciliation:
    """Classify one vector scope without broad collection-wide deletion.

    The caller can turn ``stale`` into exact outbox delete events after the
    desired relational state has been validated and committed.
    """

    current = _validated_states(existing)
    target = _validated_states(desired)
    _validate_shared_scope(current, target)
    existing_by_key = _index_by_entity_key(current)
    desired_by_key = _index_by_entity_key(target)

    unchanged: list[VectorIndexState] = []
    changed: list[VectorIndexState] = []
    new: list[VectorIndexState] = []
    for entity_key in sorted(desired_by_key):
        candidate = desired_by_key[entity_key]
        previous = existing_by_key.get(entity_key)
        if previous is None:
            new.append(candidate)
        elif _same_index_projection(previous, candidate) and previous.sync_status is VectorSyncStatus.SYNCED:
            unchanged.append(candidate)
        else:
            changed.append(candidate)

    stale = [
        existing_by_key[entity_key]
        for entity_key in sorted(existing_by_key)
        if entity_key not in desired_by_key
    ]
    return VectorStateReconciliation(
        unchanged=tuple(unchanged),
        changed=tuple(changed),
        new=tuple(new),
        stale=tuple(stale),
    )


class SqliteVectorIndexStateRepository:
    """Persist synced vector identities independently from Chroma."""

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

    async def mark_synced(self, state: VectorIndexState) -> VectorIndexState:
        if not isinstance(state, VectorIndexState):
            raise TypeError("state must be a VectorIndexState")
        timestamp = self._timestamp()
        synced = replace(
            state,
            sync_status=VectorSyncStatus.SYNCED,
            last_synced_at=timestamp,
        )
        await asyncio.to_thread(self._mark_synced, synced)
        return synced

    async def list_synced(
        self,
        *,
        entity_type: str,
        collection_name: str,
        index_version: str,
        document_ref: str | None = None,
    ) -> tuple[VectorIndexState, ...]:
        _validate_scope_values(entity_type, collection_name, index_version, document_ref)
        if entity_type == "chunk" and document_ref is None:
            raise ValueError("chunk state queries require document_ref")
        return await asyncio.to_thread(
            self._list_synced,
            entity_type,
            collection_name,
            index_version,
            document_ref,
        )

    async def plan_reconciliation(
        self,
        *,
        entity_type: str,
        collection_name: str,
        index_version: str,
        desired: Sequence[VectorIndexState],
        document_ref: str | None = None,
    ) -> VectorStateReconciliation:
        existing = await self.list_synced(
            entity_type=entity_type,
            collection_name=collection_name,
            index_version=index_version,
            document_ref=document_ref,
        )
        return reconcile_vector_states(existing, desired)

    async def remove_record(
        self,
        *,
        collection_name: str,
        chroma_record_id: str,
        document_ref: str | None = None,
        index_version: str | None = None,
    ) -> None:
        _require_non_blank("collection_name", collection_name)
        _require_non_blank("chroma_record_id", chroma_record_id)
        _validate_optional_document_ref(document_ref)
        _validate_optional_non_blank("index_version", index_version)
        await asyncio.to_thread(
            self._remove_record,
            collection_name,
            chroma_record_id,
            document_ref,
            index_version,
        )

    def _mark_synced(self, state: VectorIndexState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            existing = connection.execute(
                """
                SELECT chroma_record_id, document_ref
                FROM vector_index_state
                WHERE entity_type = ? AND entity_key = ?
                  AND collection_name = ? AND index_version = ?
                """,
                (
                    state.entity_type,
                    state.entity_key,
                    state.collection_name,
                    state.index_version,
                ),
            ).fetchone()
            if existing is not None and existing != (
                state.chroma_record_id,
                state.document_ref,
            ):
                raise ValueError("vector state already exists with a different identity")
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO vector_index_state
                        (entity_type, entity_key, collection_name, chroma_record_id,
                         embedding_input_hash, embedding_model, embedding_dimensions,
                         index_version, sync_status, last_synced_at, document_ref,
                         source_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _state_values(state),
                )
            else:
                connection.execute(
                    """
                    UPDATE vector_index_state
                    SET embedding_input_hash = ?, embedding_model = ?,
                        embedding_dimensions = ?, sync_status = ?,
                        last_synced_at = ?, source_version = ?
                    WHERE entity_type = ? AND entity_key = ?
                      AND collection_name = ? AND index_version = ?
                    """,
                    (
                        state.embedding_input_hash,
                        state.embedding_model,
                        state.embedding_dimensions,
                        state.sync_status.value,
                        state.last_synced_at,
                        state.source_version,
                        state.entity_type,
                        state.entity_key,
                        state.collection_name,
                        state.index_version,
                    ),
                )

    def _list_synced(
        self,
        entity_type: str,
        collection_name: str,
        index_version: str,
        document_ref: str | None,
    ) -> tuple[VectorIndexState, ...]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            query = """
                SELECT entity_type, entity_key, collection_name, chroma_record_id,
                       embedding_input_hash, embedding_model, embedding_dimensions,
                       index_version, sync_status, last_synced_at, document_ref,
                       source_version
                FROM vector_index_state
                WHERE entity_type = ? AND collection_name = ?
                  AND index_version = ? AND sync_status = 'synced'
            """
            parameters: list[object] = [entity_type, collection_name, index_version]
            if document_ref is not None:
                query += " AND document_ref = ?"
                parameters.append(document_ref)
            query += " ORDER BY entity_key"
            rows = connection.execute(query, parameters).fetchall()
        return tuple(_state_from_row(row) for row in rows)

    def _remove_record(
        self,
        collection_name: str,
        chroma_record_id: str,
        document_ref: str | None,
        index_version: str | None,
    ) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            query = """
                DELETE FROM vector_index_state
                WHERE collection_name = ? AND chroma_record_id = ?
            """
            parameters: list[object] = [collection_name, chroma_record_id]
            if document_ref is not None:
                query += " AND document_ref = ?"
                parameters.append(document_ref)
            if index_version is not None:
                query += " AND index_version = ?"
                parameters.append(index_version)
            connection.execute(query, parameters)

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS vector_index_state (
                entity_type TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                collection_name TEXT NOT NULL,
                chroma_record_id TEXT NOT NULL,
                embedding_input_hash TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding_dimensions INTEGER NOT NULL,
                index_version TEXT NOT NULL,
                sync_status TEXT NOT NULL,
                last_synced_at TEXT,
                document_ref TEXT,
                source_version TEXT,
                PRIMARY KEY (entity_type, entity_key, collection_name, index_version)
            )
            """
        )

    def _timestamp(self) -> str:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock must return datetime")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _validated_states(states: Sequence[VectorIndexState]) -> tuple[VectorIndexState, ...]:
    if isinstance(states, (str, bytes)) or not isinstance(states, Sequence):
        raise ValueError("vector states must be a sequence")
    normalized = tuple(states)
    if any(not isinstance(item, VectorIndexState) for item in normalized):
        raise ValueError("vector states must contain VectorIndexState values")
    return normalized


def _validate_shared_scope(
    existing: Sequence[VectorIndexState],
    desired: Sequence[VectorIndexState],
) -> None:
    states = (*existing, *desired)
    if not states:
        return
    scope = _scope(states[0])
    if any(_scope(state) != scope for state in states[1:]):
        raise ValueError("vector states must use the same vector scope")


def _scope(state: VectorIndexState) -> tuple[str, str, str, str | None]:
    return (
        state.entity_type,
        state.collection_name,
        state.index_version,
        state.document_ref if state.entity_type == "chunk" else None,
    )


def _index_by_entity_key(
    states: Sequence[VectorIndexState],
) -> dict[str, VectorIndexState]:
    indexed: dict[str, VectorIndexState] = {}
    for state in states:
        if state.entity_key in indexed:
            raise ValueError("vector states must have a unique entity_key")
        indexed[state.entity_key] = state
    return indexed


def _same_index_projection(left: VectorIndexState, right: VectorIndexState) -> bool:
    return (
        left.chroma_record_id == right.chroma_record_id
        and left.embedding_input_hash == right.embedding_input_hash
        and left.embedding_model == right.embedding_model
        and left.embedding_dimensions == right.embedding_dimensions
    )


def _validate_scope_values(
    entity_type: str,
    collection_name: str,
    index_version: str,
    document_ref: str | None,
) -> None:
    if not isinstance(entity_type, str) or entity_type not in {"chunk", "concept"}:
        raise ValueError("entity_type must be chunk or concept")
    _require_non_blank("collection_name", collection_name)
    _require_non_blank("index_version", index_version)
    _validate_optional_document_ref(document_ref)


def _state_values(state: VectorIndexState) -> tuple[object, ...]:
    return (
        state.entity_type,
        state.entity_key,
        state.collection_name,
        state.chroma_record_id,
        state.embedding_input_hash,
        state.embedding_model,
        state.embedding_dimensions,
        state.index_version,
        state.sync_status.value,
        state.last_synced_at,
        state.document_ref,
        state.source_version,
    )


def _state_from_row(row: tuple[object, ...]) -> VectorIndexState:
    return VectorIndexState(
        entity_type=row[0],
        entity_key=row[1],
        collection_name=row[2],
        chroma_record_id=row[3],
        embedding_input_hash=row[4],
        embedding_model=row[5],
        embedding_dimensions=row[6],
        index_version=row[7],
        sync_status=row[8],
        last_synced_at=row[9],
        document_ref=row[10],
        source_version=row[11],
    )


def _validate_optional_document_ref(document_ref: str | None) -> None:
    if document_ref is not None:
        _require_non_blank("document_ref", document_ref)
        if not is_safe_document_reference(document_ref):
            raise ValueError("document_ref must be a safe document reference")


def _validate_optional_non_blank(name: str, value: str | None) -> None:
    if value is not None:
        _require_non_blank(name, value)


def _require_non_blank(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
