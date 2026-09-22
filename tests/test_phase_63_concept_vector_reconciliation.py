from __future__ import annotations

import json

import pytest

from saxophone.ingestion.concept_records import (
    ConceptVectorRecord,
    build_concept_vector_record,
)
from saxophone.ingestion.vector_state import (
    SqliteVectorIndexStateRepository,
    build_concept_vector_states,
)
from saxophone.ingestion.vector_sync import VectorSyncService
from saxophone.tagging.concepts import ConceptCandidate, ConceptCandidateExample
from saxophone.tagging.vector_outbox import (
    SqliteVectorOutboxRepository,
    VectorOutboxEvent,
)


def _record(
    label: str = "Major triad",
    *,
    index_version: str = "concept-v1",
    search_text: str | None = None,
) -> ConceptVectorRecord:
    candidate = ConceptCandidate(
        canonical_label=label,
        rank=1,
        semantic_score=0.9,
        usage_count=3,
        examples=(
            ConceptCandidateExample(
                header="Triads",
                excerpt=search_text or "A major triad has three notes.",
            ),
        ),
    )
    return build_concept_vector_record(
        candidate,
        embedding=(0.1, 0.2),
        embedding_model="text-embedding-3-small",
        index_version=index_version,
    )


def test_build_concept_vector_states_is_sorted_and_global() -> None:
    states = build_concept_vector_states(
        (_record("Harmony"), _record("Major triad")),
        index_version="concept-v1",
    )

    assert [state.entity_key for state in states] == ["harmony", "major triad"]
    assert [state.chroma_record_id for state in states] == [
        _record("Harmony").record_id,
        _record("Major triad").record_id,
    ]
    assert all(state.entity_type == "concept" for state in states)
    assert all(state.collection_name == "concept_catalog" for state in states)
    assert all(state.document_ref is None for state in states)
    assert all(state.source_version is None for state in states)
    assert all(state.index_version == "concept-v1" for state in states)


@pytest.mark.parametrize(
    ("records", "index_version", "message"),
    [
        ((_record("Harmony"), _record(" harmony ")), "concept-v1", "unique normalized"),
        ((_record(index_version="concept-v2"),), "concept-v1", "index_version"),
    ],
)
def test_build_concept_vector_states_rejects_invalid_catalog_scope(
    records: tuple[ConceptVectorRecord, ...],
    index_version: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build_concept_vector_states(records, index_version=index_version)


class _ConceptIndex:
    async def upsert_chunks(self, records) -> None:
        return None

    async def delete_chunks(self, chunk_ids) -> None:
        return None

    async def upsert_concepts(self, records) -> None:
        return None

    async def delete_concepts(self, record_ids) -> None:
        return None


def _upsert_event(record: ConceptVectorRecord) -> VectorOutboxEvent:
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
    }
    return VectorOutboxEvent(
        event_id="concept-upsert",
        document_ref="concept-catalog",
        source_version="catalog-v1",
        collection="concept_catalog",
        record_id=record.record_id,
        operation="upsert",
        payload_json=json.dumps(payload),
    )


def _delete_event(record: ConceptVectorRecord) -> VectorOutboxEvent:
    return VectorOutboxEvent(
        event_id="concept-delete",
        document_ref="concept-catalog",
        source_version="catalog-v2",
        collection="concept_catalog",
        record_id=record.record_id,
        operation="delete",
        payload_json="{}",
        index_version=record.index_version,
    )


@pytest.mark.anyio
async def test_concept_sync_persists_normalized_global_state(tmp_path) -> None:
    record = _record("  Major   Triad ")
    outbox = SqliteVectorOutboxRepository(tmp_path / "outbox.sqlite")
    state = SqliteVectorIndexStateRepository(tmp_path / "state.sqlite")
    await outbox.enqueue((_upsert_event(record),))

    report = await VectorSyncService(outbox, _ConceptIndex(), state=state).sync_pending()

    assert report == {"succeeded": 1, "failed": 0}
    synced = await state.list_synced(
        entity_type="concept",
        collection_name="concept_catalog",
        index_version="concept-v1",
    )
    assert len(synced) == 1
    assert synced[0].entity_key == "major triad"
    assert synced[0].document_ref is None
    assert synced[0].source_version == "catalog-v1"

    await outbox.enqueue((_delete_event(record),))
    assert await VectorSyncService(outbox, _ConceptIndex(), state=state).sync_pending() == {
        "succeeded": 1,
        "failed": 0,
    }
    assert await state.list_synced(
        entity_type="concept",
        collection_name="concept_catalog",
        index_version="concept-v1",
    ) == ()
