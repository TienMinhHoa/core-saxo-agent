from __future__ import annotations

import json

import pytest

from saxophone.ingestion.models import ChunkIndexRecord
from saxophone.ingestion.vector_sync import VectorSyncService
from saxophone.ingestion.vector_events import (
    build_chunk_vector_upsert_event,
    build_chunk_vector_upsert_events,
)
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository


def _record(
    chunk_id: str = "chunk-1",
    *,
    document_ref: str = "doc-1",
    source_version: str = "source-v1",
    search_text: str = "Major triad.",
    metadata: dict[str, object] | None = None,
) -> ChunkIndexRecord:
    return ChunkIndexRecord(
        chunk_id=chunk_id,
        document_ref=document_ref,
        source_version=source_version,
        search_text=search_text,
        embedding=(0.1, 0.2),
        embedding_profile="embedding-v1",
        access_scope="tenant-a",
        metadata=metadata
        or {
            "heading": "Triads",
            "tagged_paragraph_ids": ("chunk-1:p1",),
            "index_version": "index-v1",
        },
    )


class RecordingVectorIndex:
    def __init__(self) -> None:
        self.records: tuple[ChunkIndexRecord, ...] = ()

    async def upsert_chunks(self, records: tuple[ChunkIndexRecord, ...]) -> None:
        self.records = tuple(records)

    async def delete_chunks(self, chunk_ids: tuple[str, ...]) -> None:
        raise AssertionError(f"unexpected delete: {chunk_ids}")


def test_chunk_vector_event_contains_replayable_record_and_stable_identity() -> None:
    event = build_chunk_vector_upsert_event(
        _record(),
        ingestion_run_id="run-1",
        index_version="index-v1",
    )

    payload = json.loads(event.payload_json)
    assert event.collection == "document_chunks"
    assert event.operation == "upsert"
    assert event.record_id == "chunk-1"
    assert event.document_ref == "doc-1"
    assert event.source_version == "source-v1"
    assert event.ingestion_run_id == "run-1"
    assert event.index_version == "index-v1"
    assert payload == {
        "record": {
            "access_scope": "tenant-a",
            "chunk_id": "chunk-1",
            "document_ref": "doc-1",
            "embedding": [0.1, 0.2],
            "embedding_profile": "embedding-v1",
            "metadata": {
                "heading": "Triads",
                "index_version": "index-v1",
                "tagged_paragraph_ids": ["chunk-1:p1"],
            },
            "search_text": "Major triad.",
            "source_version": "source-v1",
        }
    }
    assert event.event_id == build_chunk_vector_upsert_event(
        _record(),
        ingestion_run_id="run-1",
        index_version="index-v1",
    ).event_id


def test_chunk_vector_event_identity_changes_when_index_projection_changes() -> None:
    first = build_chunk_vector_upsert_event(
        _record(), ingestion_run_id="run-1", index_version="index-v1"
    )
    changed = build_chunk_vector_upsert_event(
        _record(search_text="Minor triad."),
        ingestion_run_id="run-1",
        index_version="index-v1",
    )

    assert first.event_id != changed.event_id
    assert json.loads(changed.payload_json)["record"]["search_text"] == "Minor triad."
    assert first.event_id != build_chunk_vector_upsert_event(
        _record(), ingestion_run_id="run-2", index_version="index-v1"
    ).event_id


def test_chunk_vector_event_batch_is_sorted_and_requires_one_document_scope() -> None:
    events = build_chunk_vector_upsert_events(
        (_record("chunk-2"), _record("chunk-1")),
        ingestion_run_id="run-1",
        index_version="index-v1",
    )

    assert [event.record_id for event in events] == ["chunk-1", "chunk-2"]
    assert len({event.event_id for event in events}) == 2

    with pytest.raises(ValueError, match="same document"):
        build_chunk_vector_upsert_events(
            (_record("chunk-1"), _record("chunk-2", document_ref="doc-2")),
            ingestion_run_id="run-1",
            index_version="index-v1",
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"index_version": ""}, "index_version"),
        ({"index_version": "index-v1", "ingestion_run_id": ""}, "ingestion_run_id"),
    ],
)
def test_chunk_vector_event_rejects_blank_scope_values(
    kwargs: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build_chunk_vector_upsert_event(_record(), **kwargs)


def test_chunk_vector_event_rejects_non_json_metadata() -> None:
    with pytest.raises(ValueError, match="JSON-compatible"):
        build_chunk_vector_upsert_event(
            _record(metadata={"unsupported": {"nested"}}),
            index_version="index-v1",
        )


@pytest.mark.anyio
async def test_chunk_vector_event_replays_through_vector_sync(tmp_path) -> None:
    source = _record()
    event = build_chunk_vector_upsert_event(source, index_version="index-v1")
    outbox = SqliteVectorOutboxRepository(tmp_path / "outbox.sqlite3")
    index = RecordingVectorIndex()
    await outbox.enqueue((event,))

    report = await VectorSyncService(outbox, index).sync_pending()

    assert report == {"succeeded": 1, "failed": 0}
    assert index.records[0].chunk_id == source.chunk_id
    assert index.records[0].embedding == source.embedding
    assert index.records[0].metadata["heading"] == "Triads"
    assert (await outbox.get(event.event_id)).status.value == "succeeded"
