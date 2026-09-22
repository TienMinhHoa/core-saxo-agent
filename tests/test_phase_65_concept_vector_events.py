from __future__ import annotations

import json

import pytest

from saxophone.ingestion.concept_records import (
    ConceptVectorRecord,
    build_concept_vector_record,
)
from saxophone.ingestion.vector_events import (
    build_concept_vector_upsert_event,
    build_concept_vector_upsert_events,
)
from saxophone.ingestion.vector_sync import VectorSyncService
from saxophone.tagging.concepts import ConceptCandidate, ConceptCandidateExample
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository


def _record(
    label: str = "Major triad",
    *,
    index_version: str = "concept-v1",
    excerpt: str = "A major triad has three notes.",
) -> ConceptVectorRecord:
    return build_concept_vector_record(
        ConceptCandidate(
            canonical_label=label,
            rank=1,
            semantic_score=0.9,
            usage_count=3,
            examples=(ConceptCandidateExample("Triads", excerpt),),
        ),
        embedding=(0.1, 0.2),
        embedding_model="text-embedding-3-small",
        index_version=index_version,
    )


def _scope() -> dict[str, str]:
    return {
        "catalog_ref": "concept-catalog",
        "catalog_version": "catalog-v1",
        "index_version": "concept-v1",
        "ingestion_run_id": "run-1",
    }


def test_concept_vector_event_contains_replayable_global_record() -> None:
    record = _record()

    event = build_concept_vector_upsert_event(record, **_scope())

    assert event.collection == "concept_catalog"
    assert event.operation == "upsert"
    assert event.document_ref == "concept-catalog"
    assert event.source_version == "catalog-v1"
    assert event.record_id == record.record_id
    assert event.ingestion_run_id == "run-1"
    assert event.index_version == "concept-v1"
    assert json.loads(event.payload_json) == {
        "record": {
            "record_id": record.record_id,
            "canonical_label": "Major triad",
            "normalized_label": "major triad",
            "search_text": "Major triad\nTriads: A major triad has three notes.",
            "embedding": [0.1, 0.2],
            "usage_count": 3,
            "embedding_input_hash": record.embedding_input_hash,
            "embedding_model": "text-embedding-3-small",
            "embedding_dimensions": 2,
            "index_version": "concept-v1",
            "metadata": dict(record.metadata),
        }
    }
    assert event.event_id == build_concept_vector_upsert_event(record, **_scope()).event_id


def test_concept_vector_event_identity_changes_with_projection_or_scope() -> None:
    first = build_concept_vector_upsert_event(_record(), **_scope())
    changed_projection = build_concept_vector_upsert_event(
        _record(excerpt="A major triad is built from stacked thirds."),
        **_scope(),
    )
    changed_scope = build_concept_vector_upsert_event(
        _record(),
        **{**_scope(), "ingestion_run_id": "run-2"},
    )

    assert first.event_id != changed_projection.event_id
    assert first.event_id != changed_scope.event_id


def test_concept_vector_event_batch_is_sorted_and_validates_global_scope() -> None:
    events = build_concept_vector_upsert_events(
        (_record("Harmony"), _record("Major triad")),
        **_scope(),
    )

    assert [event.record_id for event in events] == [
        _record("Harmony").record_id,
        _record("Major triad").record_id,
    ]
    assert len({event.event_id for event in events}) == 2

    with pytest.raises(ValueError, match="unique normalized"):
        build_concept_vector_upsert_events(
            (_record(), _record(" major   triad ")),
            **_scope(),
        )

    with pytest.raises(ValueError, match="index_version"):
        build_concept_vector_upsert_events(
            (_record(index_version="concept-v2"),),
            **_scope(),
        )


@pytest.mark.anyio
async def test_concept_vector_event_replays_through_vector_sync(tmp_path) -> None:
    class _VectorIndex:
        def __init__(self) -> None:
            self.records: list[ConceptVectorRecord] = []

        async def upsert_chunks(self, records) -> None:
            return None

        async def delete_chunks(self, chunk_ids) -> None:
            return None

        async def upsert_concepts(self, records) -> None:
            self.records.extend(records)

        async def delete_concepts(self, record_ids) -> None:
            return None

    record = _record()
    outbox = SqliteVectorOutboxRepository(tmp_path / "outbox.sqlite3")
    await outbox.enqueue((build_concept_vector_upsert_event(record, **_scope()),))
    vector_index = _VectorIndex()

    report = await VectorSyncService(outbox, vector_index).sync_pending()

    assert report == {"succeeded": 1, "failed": 0}
    assert vector_index.records == [record]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("catalog_ref", ""),
        ("catalog_version", ""),
        ("index_version", ""),
        ("ingestion_run_id", ""),
    ],
)
def test_concept_vector_event_rejects_blank_scope(field: str, value: str) -> None:
    with pytest.raises(ValueError, match=field):
        build_concept_vector_upsert_event(_record(), **{**_scope(), field: value})
