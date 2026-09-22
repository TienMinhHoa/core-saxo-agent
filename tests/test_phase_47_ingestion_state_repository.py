from __future__ import annotations

import asyncio

import pytest

from saxophone.ingestion.state import (
    IngestionStatus,
    SqliteIngestionStateRepository,
)


def _repository(tmp_path):
    return SqliteIngestionStateRepository(tmp_path / "state.sqlite")


def _start(repository, *, run_id="run-1", document_ref="doc-1", version="v1", source_hash="hash-1"):
    return asyncio.run(
        repository.start_or_resume(
            ingestion_run_id=run_id,
            document_ref=document_ref,
            source_version=version,
            source_hash=source_hash,
        )
    )


def test_start_or_resume_persists_processing_document_and_run(tmp_path) -> None:
    repository = _repository(tmp_path)

    run = _start(repository)
    document = asyncio.run(repository.get_document("doc-1"))

    assert run.ingestion_run_id == "run-1"
    assert run.status is IngestionStatus.PROCESSING
    assert run.completed_at is None
    assert document.source_hash == "hash-1"
    assert document.active_version is None
    assert document.status is IngestionStatus.PROCESSING
    assert document.created_at == document.updated_at


def test_start_or_resume_is_idempotent_and_reactivates_failed_run(tmp_path) -> None:
    repository = _repository(tmp_path)

    first = _start(repository)
    failed = asyncio.run(repository.mark_failed("run-1", error_code="embedding_timeout"))
    resumed = _start(repository)

    assert first.ingestion_run_id == failed.ingestion_run_id == resumed.ingestion_run_id
    assert resumed.status is IngestionStatus.PROCESSING
    assert resumed.completed_at is None
    assert resumed.error_code is None
    assert asyncio.run(repository.get_document("doc-1")).status is IngestionStatus.PROCESSING


def test_start_or_resume_rejects_identity_conflicts_and_concurrent_runs(tmp_path) -> None:
    repository = _repository(tmp_path)
    _start(repository)

    with pytest.raises(ValueError, match="different identity"):
        _start(repository, source_hash="other-hash")

    with pytest.raises(ValueError, match="active ingestion run"):
        _start(repository, run_id="run-2")


def test_ready_requires_pending_vector_sync_to_be_cleared(tmp_path) -> None:
    repository = _repository(tmp_path)
    _start(repository)

    pending = asyncio.run(repository.mark_tagged_pending_vector_sync("run-1"))
    assert pending.status is IngestionStatus.TAGGED_PENDING_VECTOR_SYNC

    with pytest.raises(ValueError, match="pending vector events"):
        asyncio.run(repository.mark_ready("run-1", pending_event_count=1))

    assert (
        asyncio.run(repository.get_document("doc-1")).status
        is IngestionStatus.TAGGED_PENDING_VECTOR_SYNC
    )

    ready = asyncio.run(repository.mark_ready("run-1", pending_event_count=0))
    document = asyncio.run(repository.get_document("doc-1"))

    assert ready.status is IngestionStatus.READY
    assert ready.completed_at is not None
    assert document.status is IngestionStatus.READY
    assert document.active_version == "v1"


def test_invalid_transitions_are_rejected_without_mutating_state(tmp_path) -> None:
    repository = _repository(tmp_path)
    _start(repository)

    with pytest.raises(ValueError, match="tagged_pending_vector_sync"):
        asyncio.run(repository.mark_ready("run-1"))

    asyncio.run(repository.mark_tagged_pending_vector_sync("run-1"))
    asyncio.run(repository.mark_ready("run-1"))

    with pytest.raises(ValueError, match="cannot transition"):
        asyncio.run(repository.mark_tagged_pending_vector_sync("run-1"))

    assert asyncio.run(repository.get_run("run-1")).status is IngestionStatus.READY


def test_lifecycle_inputs_and_missing_runs_are_validated(tmp_path) -> None:
    repository = _repository(tmp_path)

    with pytest.raises(ValueError, match="source_hash"):
        _start(repository, source_hash=" ")
    with pytest.raises(ValueError, match="ingestion_run_id"):
        _start(repository, run_id=" ")
    with pytest.raises(FileNotFoundError):
        asyncio.run(repository.get_run("missing"))
