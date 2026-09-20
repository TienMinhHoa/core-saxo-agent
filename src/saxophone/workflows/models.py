"""Typed workflow DTOs shared by application use cases and persistence adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RemoteTaskType(StrEnum):
    """Stable task names sent to the external model service."""

    PDF_EXTRACT = "pdf_extract"
    FIGURE_ANALYZE = "figure_analyze"
    STRUCTURE_LABEL = "structure_label"
    EMBED = "embed"
    PARAGRAPH_TAG = "paragraph_tag"
    TAG_RESOLVE = "tag_resolve"
    RETRIEVAL_SELECT = "retrieval_select"
    ANSWER_GENERATE = "answer_generate"


class JobStatus(StrEnum):
    """Local workflow state; it is deliberately separate from provider state."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class WorkflowJob:
    """Persistable local-to-remote request mapping.

    ``remote_job_id`` is optional while a request is queued locally.  The
    local ``job_id`` and idempotency key remain authoritative for recovery.
    """

    job_id: str
    document_ref: str
    task_type: RemoteTaskType
    idempotency_key: str
    status: JobStatus
    attempt: int
    created_at: datetime
    remote_job_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("job_id", "document_ref", "idempotency_key"):
            _require_non_blank(field_name, getattr(self, field_name))
        if self.remote_job_id is not None:
            _require_non_blank("remote_job_id", self.remote_job_id)
        if self.attempt <= 0:
            raise ValueError("attempt must be positive")


def _require_non_blank(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
