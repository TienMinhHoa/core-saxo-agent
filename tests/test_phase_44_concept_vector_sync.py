from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from saxophone.ingestion.concept_records import ConceptVectorRecord, build_concept_vector_record
from saxophone.ingestion.vector_sync import VectorSyncService
from saxophone.tagging.concepts import ConceptCandidate
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository, VectorOutboxEvent


class FakeVectorIndex:
    def __init__(self) -> None:
        self.concept_upserts: list[ConceptVectorRecord] = []
        self.concept_deletes: list[str] = []

    async def upsert_chunks(self, records) -> None:
        pass

    async def delete_chunks(self, chunk_ids) -> None:
        pass

    async def upsert_concepts(self, records) -> None:
        self.concept_upserts.extend(records)

    async def delete_concepts(self, record_ids) -> None:
        self.concept_deletes.extend(record_ids)


def _record() -> ConceptVectorRecord:
    return build_concept_vector_record(
        ConceptCandidate(
            canonical_label="Major triad",
            rank=1,
            semantic_score=0.9,
            usage_count=3,
        ),
        embedding=(0.1, 0.2),
        embedding_model="fake-embedding",
        index_version="concept-v1",
    )


def _event(record: ConceptVectorRecord, *, operation: str) -> VectorOutboxEvent:
    payload = {
        "record": {
            "record_id": record.record_id,
            "canonical_label": record.canonical_label,
            "normalized_label": record.normalized_label,
            "search_text": record.search_text,
            "embedding": list(record.embedding),
            "usage_count": record.usage_count,
            "embedding_input_hash": record.embedding_input_hash,
            "embedding_model": record.embedding_model,
            "embedding_dimensions": record.embedding_dimensions,
            "index_version": record.index_version,
            "metadata": dict(record.metadata),
        }
    } if operation == "upsert" else {}
    return VectorOutboxEvent(
        event_id=f"concept-{operation}",
        document_ref="concept-catalog",
        source_version="catalog-v1",
        collection="concept_catalog",
        record_id=record.record_id,
        operation=operation,
        payload_json=json.dumps(payload),
    )


@pytest.mark.anyio
async def test_vector_sync_applies_concept_catalog_events(tmp_path: Path) -> None:
    repository = SqliteVectorOutboxRepository(tmp_path / "outbox.sqlite")
    record = _record()
    await repository.enqueue((_event(record, operation="upsert"), _event(record, operation="delete")))
    index = FakeVectorIndex()

    report = await VectorSyncService(repository, index).sync_pending()

    assert report == {"succeeded": 2, "failed": 0}
    assert index.concept_upserts == [record]
    assert index.concept_deletes == [record.record_id]


@pytest.mark.anyio
async def test_vector_sync_rejects_concept_payload_identity_mismatch(tmp_path: Path) -> None:
    repository = SqliteVectorOutboxRepository(tmp_path / "outbox.sqlite")
    record = _record()
    event = _event(record, operation="upsert")
    mismatched_record_id = "concept::" + hashlib.sha256(b"harmony").hexdigest()
    await repository.enqueue((VectorOutboxEvent(
        event_id=event.event_id,
        document_ref=event.document_ref,
        source_version=event.source_version,
        collection=event.collection,
        record_id=mismatched_record_id,
        operation=event.operation,
        payload_json=event.payload_json,
    ),))
    index = FakeVectorIndex()

    report = await VectorSyncService(repository, index).sync_pending()

    assert report == {"succeeded": 0, "failed": 1}
    assert index.concept_upserts == []
    failed = await repository.get(event.event_id)
    assert failed.attempts == 1
    assert failed.last_error == "vector upsert payload identity does not match event"
