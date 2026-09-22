from __future__ import annotations

import asyncio

import pytest

from saxophone.ingestion.transaction import SqliteIngestionTransactionRepository
from saxophone.tagging.models import ContentRole, ParagraphConceptRole
from saxophone.tagging.sqlite_repository import SqliteTaggingRepository
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository, VectorOutboxEvent


def _event(
    *,
    event_id: str,
    source_version: str,
    operation: str,
    record_id: str,
    payload_json: str,
    index_version: str = "index-v1",
    document_ref: str = "doc-1",
) -> VectorOutboxEvent:
    return VectorOutboxEvent(
        event_id=event_id,
        ingestion_run_id="run-58",
        document_ref=document_ref,
        source_version=source_version,
        collection="document_chunks",
        record_id=record_id,
        operation=operation,
        payload_json=payload_json,
        index_version=index_version,
    )


def _relation(
    paragraph_id: str,
    concept: str,
    role: ContentRole = ContentRole.DEFINITION,
) -> ParagraphConceptRole:
    return ParagraphConceptRole(paragraph_id, concept, role)


def test_document_commit_replaces_prior_version_and_accepts_exact_stale_delete(
    tmp_path,
) -> None:
    database = tmp_path / "ingestion.sqlite3"
    tagging = SqliteTaggingRepository(database)
    outbox = SqliteVectorOutboxRepository(database)
    transaction = SqliteIngestionTransactionRepository(database)

    asyncio.run(
        tagging.replace_relations(
            "doc-1",
            "source-v1",
            (_relation("chunk-old:p1", "Old concept"),),
        )
    )
    asyncio.run(
        tagging.replace_relations(
            "doc-2",
            "source-v1",
            (_relation("chunk-sibling:p1", "Sibling concept", ContentRole.EXAMPLE),),
        )
    )
    upsert = _event(
        event_id="upsert-new",
        source_version="source-v2",
        operation="upsert",
        record_id="chunk-new",
        payload_json='{"record":"new"}',
    )
    stale_delete = _event(
        event_id="delete-old",
        source_version="source-v1",
        operation="delete",
        record_id="chunk-old",
        payload_json="{}",
    )

    asyncio.run(
        transaction.commit_document(
            document_ref="doc-1",
            source_version="source-v2",
            previous_source_versions=("source-v1",),
            paragraph_ids=("chunk-new:p1",),
            relations=(_relation("chunk-new:p1", "New concept", ContentRole.PROCEDURE),),
            outbox_events=(upsert, stale_delete),
        )
    )

    assert asyncio.run(tagging.list_relations("doc-1", "source-v1")) == ()
    assert asyncio.run(tagging.list_relations("doc-1", "source-v2")) == (
        _relation("chunk-new:p1", "New concept", ContentRole.PROCEDURE),
    )
    assert asyncio.run(tagging.list_relations("doc-2", "source-v1")) == (
        _relation("chunk-sibling:p1", "Sibling concept", ContentRole.EXAMPLE),
    )
    assert asyncio.run(outbox.list_pending()) == (stale_delete, upsert)

    # Replaying the same document commit must reuse both stable event identities.
    asyncio.run(
        transaction.commit_document(
            document_ref="doc-1",
            source_version="source-v2",
            previous_source_versions=("source-v1",),
            paragraph_ids=("chunk-new:p1",),
            relations=(_relation("chunk-new:p1", "New concept", ContentRole.PROCEDURE),),
            outbox_events=(upsert, stale_delete),
        )
    )
    assert asyncio.run(outbox.list_pending()) == (stale_delete, upsert)


def test_document_commit_rolls_back_relation_replacement_on_event_conflict(tmp_path) -> None:
    database = tmp_path / "ingestion.sqlite3"
    tagging = SqliteTaggingRepository(database)
    outbox = SqliteVectorOutboxRepository(database)
    transaction = SqliteIngestionTransactionRepository(database)
    old_relation = _relation("chunk-old:p1", "Old concept")
    staged_relation = _relation("chunk-staged:p1", "Staged concept", ContentRole.EXAMPLE)
    conflicting_event = _event(
        event_id="event-conflict",
        source_version="source-v2",
        operation="upsert",
        record_id="chunk-staged",
        payload_json='{"record":"old"}',
    )

    asyncio.run(tagging.replace_relations("doc-1", "source-v1", (old_relation,)))
    asyncio.run(tagging.replace_relations("doc-1", "source-v2", (staged_relation,)))
    asyncio.run(outbox.enqueue((conflicting_event,)))

    with pytest.raises(ValueError, match="event_id already exists with different payload or scope"):
        asyncio.run(
            transaction.commit_document(
                document_ref="doc-1",
                source_version="source-v2",
                previous_source_versions=("source-v1",),
                paragraph_ids=("chunk-new:p1",),
                relations=(_relation("chunk-new:p1", "New concept"),),
                outbox_events=(
                    _event(
                        event_id="event-conflict",
                        source_version="source-v2",
                        operation="upsert",
                        record_id="chunk-staged",
                        payload_json='{"record":"new"}',
                    ),
                ),
            )
        )

    assert asyncio.run(tagging.list_relations("doc-1", "source-v1")) == (old_relation,)
    assert asyncio.run(tagging.list_relations("doc-1", "source-v2")) == (staged_relation,)
    assert asyncio.run(outbox.get("event-conflict")) == conflicting_event


def test_document_commit_rejects_foreign_or_mismatched_upsert_before_mutation(tmp_path) -> None:
    database = tmp_path / "ingestion.sqlite3"
    tagging = SqliteTaggingRepository(database)
    transaction = SqliteIngestionTransactionRepository(database)
    previous = _relation("chunk-old:p1", "Old concept")
    asyncio.run(tagging.replace_relations("doc-1", "source-v1", (previous,)))

    foreign_event = _event(
        event_id="foreign-event",
        source_version="source-v2",
        operation="upsert",
        record_id="chunk-new",
        payload_json='{"record":"new"}',
        document_ref="doc-2",
    )
    with pytest.raises(ValueError, match="outbox events must match the document scope"):
        asyncio.run(
            transaction.commit_document(
                document_ref="doc-1",
                source_version="source-v2",
                previous_source_versions=("source-v1",),
                paragraph_ids=("chunk-new:p1",),
                relations=(_relation("chunk-new:p1", "New concept"),),
                outbox_events=(foreign_event,),
            )
        )

    mismatched_upsert = _event(
        event_id="wrong-version",
        source_version="source-v1",
        operation="upsert",
        record_id="chunk-new",
        payload_json='{"record":"new"}',
    )
    with pytest.raises(ValueError, match="upsert events must match the new source version"):
        asyncio.run(
            transaction.commit_document(
                document_ref="doc-1",
                source_version="source-v2",
                previous_source_versions=("source-v1",),
                paragraph_ids=("chunk-new:p1",),
                relations=(_relation("chunk-new:p1", "New concept"),),
                outbox_events=(mismatched_upsert,),
            )
        )

    assert asyncio.run(tagging.list_relations("doc-1", "source-v1")) == (previous,)
