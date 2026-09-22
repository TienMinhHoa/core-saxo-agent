from __future__ import annotations

import asyncio

import pytest

from saxophone.ingestion.transaction import SqliteIngestionTransactionRepository
from saxophone.tagging.models import ContentRole, ParagraphConceptRole
from saxophone.tagging.sqlite_repository import SqliteTaggingRepository
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository, VectorOutboxEvent


def _event(*, event_id: str = "event-1", payload: str = '{"record":"chunk-1"}') -> VectorOutboxEvent:
    return VectorOutboxEvent(
        event_id=event_id,
        ingestion_run_id="run-1",
        document_ref="doc-1",
        source_version="v2",
        collection="document_chunks",
        record_id="chunk-1",
        operation="upsert",
        payload_json=payload,
        index_version="index-v1",
    )


def test_chunk_commit_replaces_only_scoped_relations_and_enqueues_events(tmp_path) -> None:
    database = tmp_path / "ingestion.sqlite3"
    tagging = SqliteTaggingRepository(database)
    outbox = SqliteVectorOutboxRepository(database)
    transaction = SqliteIngestionTransactionRepository(database)
    sibling = ParagraphConceptRole("chunk:p2", "Melody", ContentRole.EXAMPLE)

    asyncio.run(tagging.replace_relations("doc-1", "v2", (sibling,)))
    event = _event()
    asyncio.run(
        transaction.commit_chunk(
            document_ref="doc-1",
            source_version="v2",
            paragraph_ids=("chunk:p1",),
            relations=(ParagraphConceptRole("chunk:p1", "Harmony", ContentRole.DEFINITION),),
            outbox_events=(event,),
        )
    )

    assert asyncio.run(tagging.list_relations("doc-1", "v2")) == (
        ParagraphConceptRole("chunk:p1", "Harmony", ContentRole.DEFINITION),
        sibling,
    )
    assert asyncio.run(outbox.list_pending()) == (event,)


def test_chunk_commit_is_idempotent_for_matching_outbox_events(tmp_path) -> None:
    database = tmp_path / "ingestion.sqlite3"
    transaction = SqliteIngestionTransactionRepository(database)
    event = _event()
    relation = ParagraphConceptRole("chunk:p1", "Harmony", ContentRole.DEFINITION)

    for _ in range(2):
        asyncio.run(
            transaction.commit_chunk(
                document_ref="doc-1",
                source_version="v2",
                paragraph_ids=("chunk:p1",),
                relations=(relation,),
                outbox_events=(event,),
            )
        )

    assert asyncio.run(SqliteVectorOutboxRepository(database).list_pending()) == (event,)


def test_chunk_commit_rolls_back_relations_when_outbox_conflicts(tmp_path) -> None:
    database = tmp_path / "ingestion.sqlite3"
    tagging = SqliteTaggingRepository(database)
    outbox = SqliteVectorOutboxRepository(database)
    transaction = SqliteIngestionTransactionRepository(database)
    previous_relation = ParagraphConceptRole("chunk:p1", "Harmony", ContentRole.DEFINITION)
    previous_event = _event(payload='{"record":"old"}')

    asyncio.run(tagging.replace_relations("doc-1", "v2", (previous_relation,)))
    asyncio.run(outbox.enqueue((previous_event,)))

    with pytest.raises(ValueError, match="event_id already exists with different payload"):
        asyncio.run(
            transaction.commit_chunk(
                document_ref="doc-1",
                source_version="v2",
                paragraph_ids=("chunk:p1",),
                relations=(ParagraphConceptRole("chunk:p1", "Harmony", ContentRole.PROCEDURE),),
                outbox_events=(_event(payload='{"record":"new"}'),),
            )
        )

    assert asyncio.run(tagging.list_relations("doc-1", "v2")) == (previous_relation,)
    assert asyncio.run(outbox.get(previous_event.event_id)) == previous_event


def test_chunk_commit_rejects_foreign_event_before_mutating_database(tmp_path) -> None:
    database = tmp_path / "ingestion.sqlite3"
    tagging = SqliteTaggingRepository(database)
    transaction = SqliteIngestionTransactionRepository(database)
    previous_relation = ParagraphConceptRole("chunk:p1", "Harmony", ContentRole.DEFINITION)

    asyncio.run(tagging.replace_relations("doc-1", "v2", (previous_relation,)))
    foreign_event = VectorOutboxEvent(
        event_id="event-foreign",
        document_ref="other-doc",
        source_version="v2",
        collection="document_chunks",
        record_id="chunk-1",
        operation="upsert",
        payload_json="{}",
    )

    with pytest.raises(ValueError, match="outbox events must match the commit scope"):
        asyncio.run(
            transaction.commit_chunk(
                document_ref="doc-1",
                source_version="v2",
                paragraph_ids=("chunk:p1",),
                relations=(),
                outbox_events=(foreign_event,),
            )
        )

    assert asyncio.run(tagging.list_relations("doc-1", "v2")) == (previous_relation,)
