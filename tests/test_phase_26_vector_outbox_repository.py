from __future__ import annotations

import asyncio

import pytest

from saxophone.tagging.vector_outbox import (
    OutboxStatus,
    VectorOutboxEvent,
    SqliteVectorOutboxRepository,
)


def event(*, event_id: str = "evt-1", payload: str = '{"id":"chunk-1"}') -> VectorOutboxEvent:
    return VectorOutboxEvent(
        event_id=event_id,
        document_ref="doc-1",
        source_version="v1",
        collection="document_chunks",
        record_id="chunk-1",
        operation="upsert",
        payload_json=payload,
    )


def test_outbox_enqueue_is_idempotent_and_pending_reads_are_deterministic(tmp_path) -> None:
    repository = SqliteVectorOutboxRepository(tmp_path / "tagging.sqlite3")
    item = event()

    asyncio.run(repository.enqueue((item, item)))

    assert asyncio.run(repository.list_pending()) == (item,)


def test_outbox_status_transitions_preserve_retry_error_and_attempt_count(tmp_path) -> None:
    repository = SqliteVectorOutboxRepository(tmp_path / "tagging.sqlite3")
    asyncio.run(repository.enqueue((event(),)))

    asyncio.run(repository.mark_failed("evt-1", "timeout"))
    failed = asyncio.run(repository.get("evt-1"))
    assert failed.status is OutboxStatus.FAILED
    assert failed.attempts == 1
    assert failed.last_error == "timeout"

    asyncio.run(repository.requeue("evt-1"))
    asyncio.run(repository.mark_succeeded("evt-1"))
    succeeded = asyncio.run(repository.get("evt-1"))
    assert succeeded.status is OutboxStatus.SUCCEEDED
    assert succeeded.attempts == 1
    assert asyncio.run(repository.list_pending()) == ()


def test_outbox_rejects_same_event_id_with_different_payload(tmp_path) -> None:
    repository = SqliteVectorOutboxRepository(tmp_path / "tagging.sqlite3")
    asyncio.run(repository.enqueue((event(),)))

    with pytest.raises(ValueError, match="event_id already exists with different payload"):
        asyncio.run(repository.enqueue((event(payload='{"id":"changed"}'),)))
