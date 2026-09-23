"""SQLite-backed content-addressed reuse for chunk tagging and embeddings."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

from saxophone.tagging.chunk_models import (
    ChunkParagraphTaggingResult,
    ChunkTaggingLabel,
    ChunkTaggingRequest,
    ChunkTaggingResult,
)

from .models import ChunkIndexRecord, IndexInputRecord
from .ports import EmbeddingReuseStore


@dataclass(frozen=True, slots=True)
class ContentFingerprint:
    """Exact UTF-8 content identity with independent collision checks."""

    sha256: str
    md5: str
    byte_length: int

    @classmethod
    def from_text(cls, text: str) -> ContentFingerprint:
        if not isinstance(text, str) or not text:
            raise ValueError("content must be a non-empty string")
        encoded = text.encode("utf-8")
        return cls(
            sha256=hashlib.sha256(encoded).hexdigest(),
            md5=hashlib.md5(encoded).hexdigest(),  # noqa: S324 - collision guard only
            byte_length=len(encoded),
        )


class ContentReservationStatus(str, Enum):
    RESERVED = "reserved"
    PROCESSING = "processing"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class ContentReservation:
    """Outcome of atomically claiming one content-processing cache key."""

    fingerprint: ContentFingerprint
    tagging_input_sha256: str
    tagging_profile: str
    embedding_profile: str
    status: ContentReservationStatus
    reservation_token: str | None = None
    cached_result: ChunkTaggingResult | None = None
    recovered_stale_processing: bool = False

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (
            self.fingerprint.sha256,
            self.tagging_input_sha256,
            self.tagging_profile,
            self.embedding_profile,
        )


class SqliteContentLedger(EmbeddingReuseStore):
    """Reuse completed chunk work globally while retaining target provenance."""

    content_addressed = True

    def __init__(
        self,
        path: Path,
        *,
        processing_timeout: timedelta = timedelta(minutes=60),
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if not isinstance(path, Path) or path.name in {"", ".", ".."}:
            raise ValueError("path must name a SQLite database file")
        if path.exists() and path.is_dir():
            raise ValueError("path must be a file")
        if not isinstance(processing_timeout, timedelta) or processing_timeout <= timedelta(0):
            raise ValueError("processing_timeout must be a positive timedelta")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._path = path.absolute()
        self._processing_timeout = processing_timeout
        self._clock = clock

    @property
    def path(self) -> Path:
        return self._path

    async def reserve(
        self,
        content: str,
        *,
        tagging_profile: str,
        embedding_profile: str,
        request: ChunkTaggingRequest,
    ) -> ContentReservation:
        _require_non_blank("tagging_profile", tagging_profile)
        _require_non_blank("embedding_profile", embedding_profile)
        if not isinstance(request, ChunkTaggingRequest):
            raise TypeError("request must be a ChunkTaggingRequest")
        fingerprint = ContentFingerprint.from_text(content)
        input_sha256 = _tagging_input_sha256(request)
        now = _utc_datetime(self._clock())
        return await asyncio.to_thread(
            self._reserve,
            fingerprint,
            tagging_profile.strip(),
            embedding_profile.strip(),
            input_sha256,
            request,
            now,
        )

    async def complete(
        self,
        reservation: ContentReservation,
        *,
        request: ChunkTaggingRequest,
        result: ChunkTaggingResult,
        embedding: Sequence[float],
    ) -> None:
        if not isinstance(reservation, ContentReservation):
            raise TypeError("reservation must be a ContentReservation")
        if reservation.status is not ContentReservationStatus.RESERVED:
            raise ValueError("only reserved content can be completed")
        if not reservation.reservation_token:
            raise ValueError("reserved content must include a reservation token")
        if not isinstance(request, ChunkTaggingRequest):
            raise TypeError("request must be a ChunkTaggingRequest")
        if not isinstance(result, ChunkTaggingResult):
            raise TypeError("result must be a ChunkTaggingResult")
        result.validate_against(request)
        normalized_embedding = _normalize_embedding(embedding)
        await asyncio.to_thread(
            self._complete,
            reservation,
            _encode_result(result),
            normalized_embedding,
            _utc_datetime(self._clock()),
        )

    async def fail(self, reservation: ContentReservation) -> None:
        if not isinstance(reservation, ContentReservation):
            raise TypeError("reservation must be a ContentReservation")
        if reservation.status is not ContentReservationStatus.RESERVED:
            return
        await asyncio.to_thread(
            self._fail,
            reservation,
            _utc_datetime(self._clock()),
        )

    async def find(
        self,
        records: Sequence[IndexInputRecord],
    ) -> Mapping[str, ChunkIndexRecord]:
        normalized = tuple(records)
        if any(not isinstance(record, IndexInputRecord) for record in normalized):
            raise TypeError("records must contain IndexInputRecord values")
        return await asyncio.to_thread(self._find, normalized)

    async def save(self, records: Sequence[ChunkIndexRecord]) -> None:
        """Completion persists vectors atomically with tagging results."""

        normalized = tuple(records)
        if any(not isinstance(record, ChunkIndexRecord) for record in normalized):
            raise TypeError("records must contain ChunkIndexRecord values")

    def _reserve(
        self,
        fingerprint: ContentFingerprint,
        tagging_profile: str,
        embedding_profile: str,
        input_sha256: str,
        request: ChunkTaggingRequest,
        now: datetime,
    ) -> ContentReservation:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path, timeout=30) as connection:
            self._create_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            self._validate_fingerprint_rows(connection, fingerprint)
            key = (
                fingerprint.sha256,
                input_sha256,
                tagging_profile,
                embedding_profile,
            )
            row = connection.execute(
                """
                SELECT status, reservation_token, tagging_result_json, updated_at
                FROM processed_chunk_content
                WHERE content_sha256 = ? AND tagging_input_sha256 = ?
                  AND tagging_profile = ? AND embedding_profile = ?
                """,
                key,
            ).fetchone()
            if row is not None and row[0] == "ready":
                if not isinstance(row[2], str) or not row[2]:
                    raise ValueError("ready content ledger row is missing tagging result")
                return ContentReservation(
                    fingerprint,
                    input_sha256,
                    tagging_profile,
                    embedding_profile,
                    ContentReservationStatus.READY,
                    cached_result=_decode_result(row[2], request),
                )
            recovered_stale_processing = False
            if row is not None and row[0] == "processing":
                updated_at = _parse_timestamp(row[3])
                if now - updated_at < self._processing_timeout:
                    return ContentReservation(
                        fingerprint,
                        input_sha256,
                        tagging_profile,
                        embedding_profile,
                        ContentReservationStatus.PROCESSING,
                    )
                connection.execute(
                    """
                    UPDATE processed_chunk_content
                    SET status = 'failed', reservation_token = NULL,
                        tagging_result_json = NULL, embedding_json = NULL,
                        embedding_dimension = NULL, updated_at = ?
                    WHERE content_sha256 = ? AND tagging_input_sha256 = ?
                      AND tagging_profile = ? AND embedding_profile = ?
                      AND status = 'processing'
                    """,
                    (_timestamp(now), *key),
                )
                recovered_stale_processing = True

            token = uuid.uuid4().hex
            now_text = _timestamp(now)
            connection.execute(
                """
                INSERT INTO processed_chunk_content (
                    content_sha256, tagging_input_sha256, tagging_profile,
                    embedding_profile, content_md5, content_byte_length,
                    status, reservation_token, tagging_result_json,
                    embedding_json, embedding_dimension, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'processing', ?, NULL, NULL, NULL, ?, ?)
                ON CONFLICT (
                    content_sha256, tagging_input_sha256,
                    tagging_profile, embedding_profile
                ) DO UPDATE SET
                    content_md5 = excluded.content_md5,
                    content_byte_length = excluded.content_byte_length,
                    status = 'processing',
                    reservation_token = excluded.reservation_token,
                    tagging_result_json = NULL,
                    embedding_json = NULL,
                    embedding_dimension = NULL,
                    updated_at = excluded.updated_at
                """,
                (
                    *key,
                    fingerprint.md5,
                    fingerprint.byte_length,
                    token,
                    now_text,
                    now_text,
                ),
            )
            return ContentReservation(
                fingerprint,
                input_sha256,
                tagging_profile,
                embedding_profile,
                ContentReservationStatus.RESERVED,
                reservation_token=token,
                recovered_stale_processing=recovered_stale_processing,
            )

    def _complete(
        self,
        reservation: ContentReservation,
        result_json: str,
        embedding: tuple[float, ...],
        now: datetime,
    ) -> None:
        with sqlite3.connect(self._path, timeout=30) as connection:
            self._create_schema(connection)
            cursor = connection.execute(
                """
                UPDATE processed_chunk_content
                SET status = 'ready', reservation_token = NULL,
                    tagging_result_json = ?, embedding_json = ?,
                    embedding_dimension = ?, updated_at = ?
                WHERE content_sha256 = ? AND tagging_input_sha256 = ?
                  AND tagging_profile = ? AND embedding_profile = ?
                  AND status = 'processing' AND reservation_token = ?
                """,
                (
                    result_json,
                    json.dumps(embedding, separators=(",", ":")),
                    len(embedding),
                    _timestamp(now),
                    *reservation.identity,
                    reservation.reservation_token,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("content reservation is no longer owned by this processor")

    def _fail(self, reservation: ContentReservation, now: datetime) -> None:
        with sqlite3.connect(self._path, timeout=30) as connection:
            self._create_schema(connection)
            connection.execute(
                """
                UPDATE processed_chunk_content
                SET status = 'failed', reservation_token = NULL,
                    tagging_result_json = NULL, embedding_json = NULL,
                    embedding_dimension = NULL, updated_at = ?
                WHERE content_sha256 = ? AND tagging_input_sha256 = ?
                  AND tagging_profile = ? AND embedding_profile = ?
                  AND status = 'processing' AND reservation_token = ?
                """,
                (
                    _timestamp(now),
                    *reservation.identity,
                    reservation.reservation_token,
                ),
            )

    def _find(
        self,
        records: tuple[IndexInputRecord, ...],
    ) -> dict[str, ChunkIndexRecord]:
        if not records or not self._path.exists():
            return {}
        resolved: dict[str, ChunkIndexRecord] = {}
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            for record in records:
                fingerprint = ContentFingerprint.from_text(record.search_text)
                self._validate_fingerprint_rows(connection, fingerprint)
                row = connection.execute(
                    """
                    SELECT embedding_json, embedding_dimension
                    FROM processed_chunk_content
                    WHERE content_sha256 = ? AND embedding_profile = ?
                      AND status = 'ready'
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (fingerprint.sha256, record.embedding_profile),
                ).fetchone()
                if row is None:
                    continue
                embedding = _decode_embedding(row[0], row[1])
                resolved[record.chunk_id] = ChunkIndexRecord(
                    chunk_id=record.chunk_id,
                    document_ref=record.document_ref,
                    source_version=record.source_version,
                    search_text=record.search_text,
                    embedding=embedding,
                    embedding_profile=record.embedding_profile,
                    access_scope=record.access_scope,
                    metadata=record.metadata,
                )
        return resolved

    @staticmethod
    def _validate_fingerprint_rows(
        connection: sqlite3.Connection,
        fingerprint: ContentFingerprint,
    ) -> None:
        rows = connection.execute(
            """
            SELECT DISTINCT content_md5, content_byte_length
            FROM processed_chunk_content
            WHERE content_sha256 = ?
            """,
            (fingerprint.sha256,),
        ).fetchall()
        if any(
            row[0] != fingerprint.md5 or row[1] != fingerprint.byte_length
            for row in rows
        ):
            raise ValueError("content fingerprint collision or corrupt ledger row")

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_chunk_content (
                content_sha256 TEXT NOT NULL,
                tagging_input_sha256 TEXT NOT NULL,
                tagging_profile TEXT NOT NULL,
                embedding_profile TEXT NOT NULL,
                content_md5 TEXT NOT NULL,
                content_byte_length INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'failed')),
                reservation_token TEXT,
                tagging_result_json TEXT,
                embedding_json TEXT,
                embedding_dimension INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (
                    content_sha256, tagging_input_sha256,
                    tagging_profile, embedding_profile
                )
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_processed_chunk_embedding
            ON processed_chunk_content (content_sha256, embedding_profile, status)
            """
        )


def remap_chunk_tagging_result(
    result: ChunkTaggingResult,
    request: ChunkTaggingRequest,
) -> ChunkTaggingResult:
    """Apply cached semantic labels to new document-local identifiers."""

    return _decode_result(_encode_result(result), request)


def _tagging_input_sha256(request: ChunkTaggingRequest) -> str:
    payload = [
        {
            "text": item.paragraph.text,
            "heading_path": item.paragraph.heading_path,
            "existing_candidates": item.existing_candidates,
            "previous_context": item.previous_context,
            "next_context": item.next_context,
            "image_context": item.image_context,
        }
        for item in request.paragraphs
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _encode_result(result: ChunkTaggingResult) -> str:
    payload = {
        "chunk_new_concepts": result.chunk_new_concepts,
        "paragraphs": [
            {
                "labels": [
                    {
                        "generated_concept": label.generated_concept,
                        "action": label.action,
                        "resolved_concept": label.resolved_concept,
                        "roles": [role.value for role in label.roles],
                    }
                    for label in paragraph.labels
                ]
            }
            for paragraph in result.paragraphs
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_result(payload_json: str, request: ChunkTaggingRequest) -> ChunkTaggingResult:
    try:
        payload = json.loads(payload_json)
        paragraphs = payload["paragraphs"]
        concepts = payload["chunk_new_concepts"]
        if not isinstance(paragraphs, list) or len(paragraphs) != len(request.paragraphs):
            raise ValueError("cached paragraph shape does not match request")
        result = ChunkTaggingResult(
            request.chunk_id,
            tuple(concepts),
            tuple(
                ChunkParagraphTaggingResult(
                    requested.paragraph.paragraph_id,
                    tuple(
                        ChunkTaggingLabel(
                            label["generated_concept"],
                            label["action"],
                            label["resolved_concept"],
                            tuple(label["roles"]),
                        )
                        for label in cached["labels"]
                    ),
                )
                for cached, requested in zip(paragraphs, request.paragraphs)
            ),
        )
        result.validate_against(request)
        return result
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("content ledger tagging result is corrupt") from error


def _normalize_embedding(embedding: Sequence[float]) -> tuple[float, ...]:
    values = tuple(embedding)
    if not values:
        raise ValueError("embedding must not be empty")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise ValueError("embedding values must be numbers")
    return tuple(float(value) for value in values)


def _decode_embedding(payload_json: object, dimension: object) -> tuple[float, ...]:
    try:
        if not isinstance(payload_json, str):
            raise ValueError("embedding payload must be JSON")
        embedding = _normalize_embedding(json.loads(payload_json))
        if not isinstance(dimension, int) or len(embedding) != dimension:
            raise ValueError("embedding dimension does not match payload")
        return embedding
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("content ledger embedding is corrupt") from error


def _timestamp(value: datetime) -> str:
    return _utc_datetime(value).isoformat()


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("content ledger timestamp is corrupt")
    try:
        return _utc_datetime(datetime.fromisoformat(value))
    except ValueError as error:
        raise ValueError("content ledger timestamp is corrupt") from error


def _utc_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _require_non_blank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")
