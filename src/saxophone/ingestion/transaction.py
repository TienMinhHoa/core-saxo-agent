"""Atomic SQLite commit boundary for one tagged ingestion chunk."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from saxophone.documents.policies import is_safe_document_reference
from saxophone.tagging.models import ParagraphConceptRole
from saxophone.tagging.models import ParagraphBlock
from saxophone.retrieval.sqlite_context import SqliteRetrievalContextRepository
from saxophone.tagging.sqlite_repository import SqliteTaggingRepository
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository, VectorOutboxEvent

from .models import IngestionSourceChunk


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

    async def commit_document(
        self,
        *,
        document_ref: str,
        source_version: str,
        paragraph_ids: Sequence[str],
        relations: Sequence[ParagraphConceptRole],
        outbox_events: Sequence[VectorOutboxEvent],
        concept_outbox_events: Sequence[VectorOutboxEvent] = (),
        previous_source_versions: Sequence[str] = (),
        chunks: Sequence[IngestionSourceChunk] = (),
        paragraphs: Sequence[ParagraphBlock] = (),
    ) -> None:
        """Replace one document version and enqueue vector changes atomically.

        Delete events may refer to a previous source version because they target
        stale vector identities, while upsert events must belong to the new one.
        """

        normalized_previous_versions = self._validate_document_inputs(
            document_ref=document_ref,
            source_version=source_version,
            paragraph_ids=paragraph_ids,
            relations=relations,
            outbox_events=outbox_events,
            concept_outbox_events=concept_outbox_events,
            previous_source_versions=previous_source_versions,
            chunks=chunks,
            paragraphs=paragraphs,
        )
        await asyncio.to_thread(
            self._commit_document,
            document_ref,
            source_version,
            normalized_previous_versions,
            tuple(paragraph_ids),
            tuple(relations),
            tuple(outbox_events),
            tuple(concept_outbox_events),
            tuple(chunks),
            tuple(paragraphs),
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

    def _commit_document(
        self,
        document_ref: str,
        source_version: str,
        previous_source_versions: tuple[str, ...],
        paragraph_ids: tuple[str, ...],
        relations: tuple[ParagraphConceptRole, ...],
        outbox_events: tuple[VectorOutboxEvent, ...],
        concept_outbox_events: tuple[VectorOutboxEvent, ...],
        chunks: tuple[IngestionSourceChunk, ...],
        paragraphs: tuple[ParagraphBlock, ...],
    ) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            SqliteTaggingRepository._create_schema(connection)
            SqliteVectorOutboxRepository._create_schema(connection)
            SqliteRetrievalContextRepository._create_schema(connection)

            connection.execute(
                "DELETE FROM paragraph_concept_roles WHERE document_ref = ? AND source_version = ?",
                (document_ref, source_version),
            )
            if previous_source_versions:
                placeholders = ", ".join("?" for _ in previous_source_versions)
                connection.execute(
                    f"""
                    DELETE FROM paragraph_concept_roles
                    WHERE document_ref = ? AND source_version IN ({placeholders})
                    """,
                    (document_ref, *previous_source_versions),
                )
                connection.execute(
                    f"DELETE FROM source_paragraphs WHERE document_ref = ? AND source_version IN ({placeholders})",
                    (document_ref, *previous_source_versions),
                )
                connection.execute(
                    f"DELETE FROM source_chunks WHERE document_ref = ? AND source_version IN ({placeholders})",
                    (document_ref, *previous_source_versions),
                )
            if chunks:
                connection.execute(
                    "DELETE FROM source_paragraphs WHERE document_ref = ? AND source_version = ?",
                    (document_ref, source_version),
                )
                connection.execute(
                    "DELETE FROM source_chunks WHERE document_ref = ? AND source_version = ?",
                    (document_ref, source_version),
                )
                connection.executemany(
                    """
                    INSERT INTO source_chunks
                        (document_ref, source_version, chunk_id, search_text, metadata_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            chunk.document_ref,
                            chunk.source_version,
                            chunk.chunk_id,
                            chunk.search_text,
                            json.dumps(dict(chunk.metadata), ensure_ascii=False, sort_keys=True),
                        )
                        for chunk in chunks
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO source_paragraphs
                        (document_ref, source_version, paragraph_id, chunk_id,
                         order_index, text, exact_content_hash,
                         normalized_identity_hash, heading_path_json, image_refs_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            document_ref,
                            source_version,
                            paragraph.paragraph_id,
                            paragraph.chunk_id,
                            paragraph.ordinal,
                            paragraph.text,
                            paragraph.exact_content_hash,
                            paragraph.normalized_identity_hash,
                            json.dumps(paragraph.heading_path, ensure_ascii=False),
                            json.dumps(paragraph.image_refs, ensure_ascii=False),
                        )
                        for paragraph in paragraphs
                    ),
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
            for event in concept_outbox_events:
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

    @staticmethod
    def _validate_document_inputs(
        *,
        document_ref: str,
        source_version: str,
        paragraph_ids: Sequence[str],
        relations: Sequence[ParagraphConceptRole],
        outbox_events: Sequence[VectorOutboxEvent],
        concept_outbox_events: Sequence[VectorOutboxEvent],
        previous_source_versions: Sequence[str],
        chunks: Sequence[IngestionSourceChunk],
        paragraphs: Sequence[ParagraphBlock],
    ) -> tuple[str, ...]:
        if not isinstance(document_ref, str) or not document_ref.strip():
            raise ValueError("document_ref must not be blank")
        if not is_safe_document_reference(document_ref):
            raise ValueError("document_ref must be a safe document reference")
        if not isinstance(source_version, str) or not source_version.strip():
            raise ValueError("source_version must not be blank")
        if (
            isinstance(previous_source_versions, (str, bytes))
            or not isinstance(previous_source_versions, Sequence)
        ):
            raise ValueError("previous_source_versions must contain non-blank strings")
        normalized_previous_versions = tuple(previous_source_versions)
        if any(not isinstance(item, str) or not item.strip() for item in normalized_previous_versions):
            raise ValueError("previous_source_versions must contain non-blank strings")
        if len(normalized_previous_versions) != len(set(normalized_previous_versions)):
            raise ValueError("previous_source_versions must be unique")
        if source_version in normalized_previous_versions:
            raise ValueError("previous_source_versions must not contain the new source version")

        normalized_paragraph_ids = SqliteIngestionTransactionRepository._validate_paragraph_ids(
            paragraph_ids
        )
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
        for event in normalized_events:
            if event.document_ref != document_ref:
                raise ValueError("outbox events must match the document scope")
            if event.operation == "upsert" and event.source_version != source_version:
                raise ValueError("upsert events must match the new source version")
            if (
                event.operation == "delete"
                and event.source_version != source_version
                and event.source_version not in normalized_previous_versions
            ):
                raise ValueError("delete events must target the new or previous source version")
        normalized_concept_events = tuple(concept_outbox_events)
        if any(not isinstance(item, VectorOutboxEvent) for item in normalized_concept_events):
            raise ValueError("concept outbox events must contain VectorOutboxEvent values")
        if len({item.event_id for item in normalized_concept_events}) != len(normalized_concept_events):
            raise ValueError("concept outbox events must not contain duplicate event IDs")
        if len({item.event_id for item in (*normalized_events, *normalized_concept_events)}) != (
            len(normalized_events) + len(normalized_concept_events)
        ):
            raise ValueError("outbox events must not contain duplicate event IDs")
        for event in normalized_concept_events:
            if event.collection != "concept_catalog":
                raise ValueError("concept outbox events must target concept_catalog")
            if event.document_ref != "concept-catalog":
                raise ValueError("concept outbox events must use the concept-catalog scope")
        SqliteIngestionTransactionRepository._validate_source_context(
            document_ref=document_ref,
            source_version=source_version,
            paragraph_ids=normalized_paragraph_ids,
            chunks=chunks,
            paragraphs=paragraphs,
        )
        return normalized_previous_versions

    @staticmethod
    def _validate_source_context(
        *,
        document_ref: str,
        source_version: str,
        paragraph_ids: Sequence[str],
        chunks: Sequence[IngestionSourceChunk],
        paragraphs: Sequence[ParagraphBlock],
    ) -> None:
        if isinstance(chunks, (str, bytes)) or not isinstance(chunks, Sequence):
            raise ValueError("chunks must be a sequence")
        if isinstance(paragraphs, (str, bytes)) or not isinstance(paragraphs, Sequence):
            raise ValueError("paragraphs must be a sequence")
        normalized_chunks = tuple(chunks)
        normalized_paragraphs = tuple(paragraphs)
        if not normalized_chunks and not normalized_paragraphs:
            return
        if not normalized_chunks or not normalized_paragraphs:
            raise ValueError("chunks and paragraphs must be provided together")
        if any(not isinstance(chunk, IngestionSourceChunk) for chunk in normalized_chunks):
            raise ValueError("chunks must contain IngestionSourceChunk values")
        if any(not isinstance(paragraph, ParagraphBlock) for paragraph in normalized_paragraphs):
            raise ValueError("paragraphs must contain ParagraphBlock values")
        chunk_ids = tuple(chunk.chunk_id for chunk in normalized_chunks)
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("chunks must have unique chunk IDs")
        if any(
            chunk.document_ref != document_ref or chunk.source_version != source_version
            for chunk in normalized_chunks
        ):
            raise ValueError("chunks must match the document commit scope")
        if {paragraph.paragraph_id for paragraph in normalized_paragraphs} != set(paragraph_ids):
            raise ValueError("paragraphs must match paragraph_ids")
        if any(paragraph.chunk_id not in set(chunk_ids) for paragraph in normalized_paragraphs):
            raise ValueError("paragraphs must belong to supplied chunks")

    @staticmethod
    def _validate_paragraph_ids(paragraph_ids: Sequence[str]) -> tuple[str, ...]:
        if isinstance(paragraph_ids, (str, bytes)) or not isinstance(paragraph_ids, Sequence):
            raise ValueError("paragraph_ids must contain non-blank strings")
        normalized = tuple(paragraph_ids)
        if not normalized or any(not isinstance(item, str) or not item.strip() for item in normalized):
            raise ValueError("paragraph_ids must contain non-blank strings")
        if len(normalized) != len(set(normalized)):
            raise ValueError("paragraph_ids must be unique")
        return normalized
