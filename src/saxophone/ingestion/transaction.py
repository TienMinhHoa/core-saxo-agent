"""Atomic SQLite commit boundary for one tagged ingestion chunk."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from saxophone.documents.policies import is_safe_document_reference
from saxophone.tagging.models import ParagraphConceptRole
from saxophone.tagging.sqlite_repository import SqliteTaggingRepository
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository, VectorOutboxEvent


class SqliteIngestionTransactionRepository:
    """Commit scoped tagging relations and vector work in one SQLite transaction."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path) or path.name in {"", ".", ".."}:
            raise ValueError("path must name a SQLite database file")
        if path.exists() and path.is_dir():
            raise ValueError("path must be a file")
        self._path = path.absolute()

    async def commit_chunk(
        self,
        *,
        document_ref: str,
        source_version: str,
        paragraph_ids: Sequence[str],
        relations: Sequence[ParagraphConceptRole],
        outbox_events: Sequence[VectorOutboxEvent],
    ) -> None:
        """Replace one paragraph scope and enqueue its vector events atomically."""

        normalized_paragraph_ids = self._validate_inputs(
            document_ref=document_ref,
            source_version=source_version,
            paragraph_ids=paragraph_ids,
            relations=relations,
            outbox_events=outbox_events,
        )
        await asyncio.to_thread(
            self._commit_chunk,
            document_ref,
            source_version,
            normalized_paragraph_ids,
            tuple(relations),
            tuple(outbox_events),
        )

    def _commit_chunk(
        self,
        document_ref: str,
        source_version: str,
        paragraph_ids: tuple[str, ...],
        relations: tuple[ParagraphConceptRole, ...],
        outbox_events: tuple[VectorOutboxEvent, ...],
    ) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            SqliteTaggingRepository._create_schema(connection)
            SqliteVectorOutboxRepository._create_schema(connection)

            placeholders = ", ".join("?" for _ in paragraph_ids)
            connection.execute(
                f"""
                DELETE FROM paragraph_concept_roles
                WHERE document_ref = ? AND source_version = ?
                  AND paragraph_id IN ({placeholders})
                """,
                (document_ref, source_version, *paragraph_ids),
            )
            connection.executemany(
                """
                INSERT INTO paragraph_concept_roles
                    (document_ref, source_version, paragraph_id, canonical_concept, content_role)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (
                        document_ref,
                        source_version,
                        relation.paragraph_id,
                        relation.canonical_concept,
                        relation.content_role.value,
                    )
                    for relation in relations
                ),
            )
            for event in outbox_events:
                self._enqueue_event(connection, event)

    @staticmethod
    def _enqueue_event(connection: sqlite3.Connection, event: VectorOutboxEvent) -> None:
        existing = connection.execute(
            """
            SELECT ingestion_run_id, document_ref, source_version, collection,
                   record_id, operation, payload_json, index_version
            FROM vector_outbox
            WHERE event_id = ?
            """,
            (event.event_id,),
        ).fetchone()
        expected = (
            event.ingestion_run_id,
            event.document_ref,
            event.source_version,
            event.collection,
            event.record_id,
            event.operation,
            event.payload_json,
            event.index_version,
        )
        if existing is not None:
            if existing != expected:
                raise ValueError("event_id already exists with different payload or scope")
            return
        connection.execute(
            """
            INSERT INTO vector_outbox
                (event_id, ingestion_run_id, document_ref, source_version,
                 collection, record_id, operation, payload_json, index_version,
                 status, attempts, last_error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.ingestion_run_id,
                event.document_ref,
                event.source_version,
                event.collection,
                event.record_id,
                event.operation,
                event.payload_json,
                event.index_version,
                event.status.value,
                event.attempts,
                event.last_error,
            ),
        )

    @staticmethod
    def _validate_inputs(
        *,
        document_ref: str,
        source_version: str,
        paragraph_ids: Sequence[str],
        relations: Sequence[ParagraphConceptRole],
        outbox_events: Sequence[VectorOutboxEvent],
    ) -> tuple[str, ...]:
        if not isinstance(document_ref, str) or not document_ref.strip():
            raise ValueError("document_ref must not be blank")
        if not is_safe_document_reference(document_ref):
            raise ValueError("document_ref must be a safe document reference")
        if not isinstance(source_version, str) or not source_version.strip():
            raise ValueError("source_version must not be blank")
        if isinstance(paragraph_ids, (str, bytes)) or not isinstance(paragraph_ids, Sequence):
            raise ValueError("paragraph_ids must contain non-blank strings")
        normalized_paragraph_ids = tuple(paragraph_ids)
        if not normalized_paragraph_ids or any(
            not isinstance(item, str) or not item.strip() for item in normalized_paragraph_ids
        ):
            raise ValueError("paragraph_ids must contain non-blank strings")
        if len(normalized_paragraph_ids) != len(set(normalized_paragraph_ids)):
            raise ValueError("paragraph_ids must be unique")

        normalized_relations = tuple(relations)
        if any(not isinstance(item, ParagraphConceptRole) for item in normalized_relations):
            raise ValueError("relations must contain ParagraphConceptRole values")
        if any(item.paragraph_id not in normalized_paragraph_ids for item in normalized_relations):
            raise ValueError("relations must belong to paragraph_ids")
        relation_keys = tuple(
            (item.paragraph_id, item.canonical_concept, item.content_role.value)
            for item in normalized_relations
        )
        if len(relation_keys) != len(set(relation_keys)):
            raise ValueError("relations must be unique")

        normalized_events = tuple(outbox_events)
        if any(not isinstance(item, VectorOutboxEvent) for item in normalized_events):
            raise ValueError("outbox_events must contain VectorOutboxEvent values")
        if len({item.event_id for item in normalized_events}) != len(normalized_events):
            raise ValueError("outbox_events must not contain duplicate event IDs")
        if any(
            item.document_ref != document_ref or item.source_version != source_version
            for item in normalized_events
        ):
            raise ValueError("outbox events must match the commit scope")
        return normalized_paragraph_ids
