from __future__ import annotations

from datetime import UTC, datetime

import pytest

from saxophone.workflows.models import JobStatus, RemoteTaskType, WorkflowJob


def test_workflow_job_preserves_the_persisted_local_to_remote_mapping() -> None:
    created_at = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)

    job = WorkflowJob(
        job_id="local-job-123",
        document_ref="document-456",
        task_type=RemoteTaskType.PDF_EXTRACT,
        idempotency_key="pdf:document-456:sha256:profile-v1",
        status=JobStatus.RUNNING,
        attempt=2,
        created_at=created_at,
        remote_job_id="remote-job-789",
    )

    assert job.job_id == "local-job-123"
    assert job.document_ref == "document-456"
    assert job.task_type is RemoteTaskType.PDF_EXTRACT
    assert job.idempotency_key == "pdf:document-456:sha256:profile-v1"
    assert job.status is JobStatus.RUNNING
    assert job.attempt == 2
    assert job.created_at == created_at
    assert job.remote_job_id == "remote-job-789"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("job_id", ""),
        ("document_ref", "  "),
        ("idempotency_key", ""),
        ("remote_job_id", "\t"),
    ],
)
def test_workflow_job_rejects_empty_persisted_identifiers(field: str, value: str) -> None:
    fields = {
        "job_id": "local-job-123",
        "document_ref": "document-456",
        "task_type": RemoteTaskType.PDF_EXTRACT,
        "idempotency_key": "pdf:document-456:sha256:profile-v1",
        "status": JobStatus.QUEUED,
        "attempt": 1,
        "created_at": datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
        "remote_job_id": None,
    }
    fields[field] = value

    with pytest.raises(ValueError, match=field):
        WorkflowJob(**fields)


@pytest.mark.parametrize("attempt", [0, -1])
def test_workflow_job_rejects_non_positive_attempts(attempt: int) -> None:
    with pytest.raises(ValueError, match="attempt"):
        WorkflowJob(
            job_id="local-job-123",
            document_ref="document-456",
            task_type=RemoteTaskType.PDF_EXTRACT,
            idempotency_key="pdf:document-456:sha256:profile-v1",
            status=JobStatus.QUEUED,
            attempt=attempt,
            created_at=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
        )
