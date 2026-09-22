"""Durable, source-version-aware persistence for the global concept catalog."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from saxophone.documents.policies import is_safe_document_reference
from saxophone.tagging.concepts import ConceptCandidateExample

from .concept_catalog import ConceptCatalogEntry


class SqliteConceptCatalogRepository:
    """Reconcile per-document observations into one deterministic catalog.

    Source-version observations make retries and re-ingestion replacements
    idempotent while the aggregate ``concepts`` table remains the retrieval
    source for the global catalog.
    """

    def __init__(
        self,
        path: Path,
        *,
        max_examples: int = 3,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(path, Path) or path.name in {"", ".", ".."}:
            raise ValueError("path must name a SQLite database file")
        if path.exists() and path.is_dir():
            raise ValueError("path must be a file")
        if isinstance(max_examples, bool) or not isinstance(max_examples, int) or max_examples < 1:
            raise ValueError("max_examples must be a positive integer")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        self._path = path.absolute()
        self._max_examples = max_examples
        self._clock = clock or _utc_now

    async def replace_document_entries(
        self,
        document_ref: str,
        source_version: str,
        entries: Sequence[ConceptCatalogEntry],
        *,
        previous_source_versions: Sequence[str] = (),
    ) -> tuple[ConceptCatalogEntry, ...]:
        """Replace one document's observations and return the global catalog."""

        normalized_previous = self._validate_inputs(
            document_ref,
            source_version,
            entries,
            previous_source_versions,
        )
        return await asyncio.to_thread(
            self._replace_document_entries,
            document_ref.strip(),
            source_version.strip(),
            tuple(entries),
            normalized_previous,
        )

    async def list_entries(self) -> tuple[ConceptCatalogEntry, ...]:
        """Return the aggregate catalog in normalized-label order."""

        return await asyncio.to_thread(self._list_entries)

    def _replace_document_entries(
        self,
        document_ref: str,
        source_version: str,
        entries: tuple[ConceptCatalogEntry, ...],
        previous_source_versions: tuple[str, ...],
    ) -> tuple[ConceptCatalogEntry, ...]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            scopes = (source_version, *previous_source_versions)
            placeholders = ", ".join("?" for _ in scopes)
            connection.execute(
                f"""
                DELETE FROM concept_catalog_observations
                WHERE document_ref = ? AND source_version IN ({placeholders})
                """,
                (document_ref, *scopes),
            )
            connection.executemany(
                """
                INSERT INTO concept_catalog_observations
                    (document_ref, source_version, normalized_label, canonical_label,
                     usage_count, examples_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        document_ref,
                        source_version,
                        entry.normalized_label,
                        entry.canonical_label,
                        entry.usage_count,
                        _encode_examples(entry.examples),
                    )
                    for entry in entries
                ),
            )
            return self._rebuild_aggregate(connection)

    def _list_entries(self) -> tuple[ConceptCatalogEntry, ...]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            return self._read_aggregate(connection)

    def _rebuild_aggregate(
        self,
        connection: sqlite3.Connection,
    ) -> tuple[ConceptCatalogEntry, ...]:
        existing_created_at = {
            normalized_label: created_at
            for normalized_label, created_at in connection.execute(
                "SELECT normalized_label, created_at FROM concepts"
            ).fetchall()
        }
        rows = connection.execute(
            """
            SELECT normalized_label, canonical_label, usage_count, examples_json,
                   document_ref, source_version
            FROM concept_catalog_observations
            ORDER BY normalized_label, document_ref, source_version, canonical_label
            """
        ).fetchall()
        grouped: dict[str, list[tuple[object, ...]]] = {}
        for row in rows:
            grouped.setdefault(row[0], []).append(row)

        now = self._timestamp()
        connection.execute("DELETE FROM concepts")
        for normalized_label in sorted(grouped):
            observations = grouped[normalized_label]
            canonical_values = {row[1] for row in observations}
            canonical_label = min(
                canonical_values,
                key=lambda value: (value.casefold(), value),
            )
            usage_count = sum(row[2] for row in observations)
            examples = _merge_examples(observations, max_examples=self._max_examples)
            first_seen_source = min(
                (row[4], row[5]) for row in observations
            )[0]
            created_at = existing_created_at.get(normalized_label, now)
            connection.execute(
                """
                INSERT INTO concepts
                    (normalized_label, canonical_label, usage_count, examples_json,
                     first_seen_source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_label,
                    canonical_label,
                    usage_count,
                    _encode_examples(examples),
                    first_seen_source,
                    created_at,
                    now,
                ),
            )
        return self._read_aggregate(connection)

    def _read_aggregate(
        self,
        connection: sqlite3.Connection,
    ) -> tuple[ConceptCatalogEntry, ...]:
        rows = connection.execute(
            """
            SELECT canonical_label, normalized_label, usage_count, examples_json
            FROM concepts
            ORDER BY normalized_label
            """
        ).fetchall()
        return tuple(
            ConceptCatalogEntry(
                canonical_label=row[0],
                normalized_label=row[1],
                usage_count=row[2],
                examples=_decode_examples(row[3]),
            )
            for row in rows
        )

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS concepts (
                normalized_label TEXT PRIMARY KEY,
                canonical_label TEXT NOT NULL,
                usage_count INTEGER NOT NULL,
                examples_json TEXT NOT NULL,
                first_seen_source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS concept_catalog_observations (
                document_ref TEXT NOT NULL,
                source_version TEXT NOT NULL,
                normalized_label TEXT NOT NULL,
                canonical_label TEXT NOT NULL,
                usage_count INTEGER NOT NULL,
                examples_json TEXT NOT NULL,
                PRIMARY KEY (document_ref, source_version, normalized_label)
            )
            """
        )

    @staticmethod
    def _validate_inputs(
        document_ref: str,
        source_version: str,
        entries: Sequence[ConceptCatalogEntry],
        previous_source_versions: Sequence[str],
    ) -> tuple[str, ...]:
        if not isinstance(document_ref, str) or not document_ref.strip():
            raise ValueError("document_ref must not be blank")
        if not is_safe_document_reference(document_ref.strip()):
            raise ValueError("document_ref must be a safe document reference")
        if not isinstance(source_version, str) or not source_version.strip():
            raise ValueError("source_version must not be blank")
        if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
            raise ValueError("entries must be a sequence")
        normalized_entries = tuple(entries)
        if any(not isinstance(entry, ConceptCatalogEntry) for entry in normalized_entries):
            raise ValueError("entries must contain ConceptCatalogEntry values")
        labels = tuple(entry.normalized_label for entry in normalized_entries)
        if len(labels) != len(set(labels)):
            raise ValueError("entries must have unique normalized labels")
        if (
            isinstance(previous_source_versions, (str, bytes))
            or not isinstance(previous_source_versions, Sequence)
        ):
            raise ValueError("previous_source_versions must be a sequence")
        normalized_previous = tuple(previous_source_versions)
        if any(not isinstance(value, str) or not value.strip() for value in normalized_previous):
            raise ValueError("previous_source_versions must contain non-blank strings")
        if len(normalized_previous) != len(set(normalized_previous)):
            raise ValueError("previous_source_versions must be unique")
        if source_version.strip() in normalized_previous:
            raise ValueError("previous_source_versions must not contain the new source version")
        return normalized_previous

    def _timestamp(self) -> str:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock must return datetime")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _merge_examples(
    observations: Sequence[tuple[object, ...]],
    *,
    max_examples: int,
) -> tuple[ConceptCandidateExample, ...]:
    unique: dict[tuple[str, str], ConceptCandidateExample] = {}
    for row in observations:
        for example in _decode_examples(row[3]):
            unique.setdefault((example.header, example.excerpt), example)
    return tuple(
        unique[key]
        for key in sorted(unique)[:max_examples]
    )


def _encode_examples(examples: Sequence[ConceptCandidateExample]) -> str:
    return json.dumps(
        [{"header": item.header, "excerpt": item.excerpt} for item in examples],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _decode_examples(value: object) -> tuple[ConceptCandidateExample, ...]:
    if not isinstance(value, str):
        raise ValueError("stored concept examples must be JSON text")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("stored concept examples must be valid JSON") from error
    if not isinstance(decoded, list):
        raise ValueError("stored concept examples must be a JSON list")
    examples: list[ConceptCandidateExample] = []
    for item in decoded:
        if not isinstance(item, dict) or set(item) != {"header", "excerpt"}:
            raise ValueError("stored concept examples have an invalid shape")
        examples.append(ConceptCandidateExample(item["header"], item["excerpt"]))
    return tuple(examples)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
