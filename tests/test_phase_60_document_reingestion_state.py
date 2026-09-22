from __future__ import annotations

from dataclasses import dataclass

import pytest

from saxophone.ingestion.models import IngestionCommand, IngestionReport
from saxophone.ingestion.services import DocumentIngestionService
from saxophone.ingestion.state import DocumentState, IngestionStatus


def _command(*, source_version: str = "source-v2") -> IngestionCommand:
    return IngestionCommand(
        document_ref="doc-1",
        source_version=source_version,
        chunking_profile="header-v1",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
    )


def _report() -> IngestionReport:
    return IngestionReport(
        document_ref="doc-1",
        source_version="source-v2",
        chunk_count=0,
        paragraph_count=0,
        tagged_paragraph_count=0,
        failed_paragraph_count=0,
        embedded_count=0,
        reused_embedding_count=0,
        skipped_count=0,
        index_version="index-v1",
        indexed=True,
        warnings=(),
        errors=(),
    )


@dataclass
class RecordingWorkflow:
    calls: list[dict[str, object]]

    async def execute(
        self,
        command,
        chunks,
        paragraphs,
        *,
        resolution_profile,
        ingestion_run_id=None,
        previous_source_versions=(),
    ):
        self.calls.append(
            {
                "command": command,
                "chunks": tuple(chunks),
                "paragraphs": tuple(paragraphs),
                "resolution_profile": resolution_profile,
                "ingestion_run_id": ingestion_run_id,
                "previous_source_versions": tuple(previous_source_versions),
            }
        )
        return _report()


class RecordingLifecycle:
    def __init__(self, document: DocumentState | None) -> None:
        self.document = document
        self.calls: list[tuple[str, object]] = []

    async def get_document(self, document_ref: str):
        self.calls.append(("get_document", document_ref))
        if self.document is None:
            raise FileNotFoundError(document_ref)
        return self.document

    async def start_or_resume(self, **kwargs):
        self.calls.append(("start_or_resume", kwargs))

    async def mark_tagged_pending_vector_sync(self, ingestion_run_id):
        self.calls.append(("mark_tagged_pending_vector_sync", ingestion_run_id))

    async def mark_ready(self, ingestion_run_id, *, pending_event_count=0):
        self.calls.append(("mark_ready", ingestion_run_id))

    async def mark_failed(self, ingestion_run_id, *, error_code):
        self.calls.append(("mark_failed", error_code))


class EmptyVectorSync:
    async def sync_pending(self, *, ingestion_run_id: str, limit: int):
        return {"succeeded": 0, "failed": 0}

    async def pending_count(self, *, ingestion_run_id: str):
        return 0


def _document(active_version: str | None) -> DocumentState:
    return DocumentState(
        document_ref="doc-1",
        source_hash="hash-1",
        active_version=active_version,
        status=IngestionStatus.READY,
        created_at="2026-09-22T00:00:00+00:00",
        updated_at="2026-09-22T00:00:00+00:00",
    )


@pytest.mark.anyio
async def test_document_ingestion_forwards_active_version_before_starting_run() -> None:
    workflow = RecordingWorkflow([])
    lifecycle = RecordingLifecycle(_document("source-v1"))
    service = DocumentIngestionService(
        workflow,
        vector_sync=EmptyVectorSync(),
        lifecycle=lifecycle,
    )

    result = await service.ingest_document(
        _command(),
        (),
        (),
        resolution_profile="resolve-v1",
        ingestion_run_id="run-60",
        source_hash="hash-2",
    )

    assert result.indexed is True
    assert workflow.calls[0]["previous_source_versions"] == ("source-v1",)
    assert [name for name, _ in lifecycle.calls[:2]] == [
        "get_document",
        "start_or_resume",
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("document", "source_version"),
    (
        (None, "source-v2"),
        (_document(None), "source-v2"),
        (_document("source-v2"), "source-v2"),
    ),
)
async def test_document_ingestion_does_not_forward_missing_or_current_version(
    document: DocumentState | None,
    source_version: str,
) -> None:
    workflow = RecordingWorkflow([])
    lifecycle = RecordingLifecycle(document)
    service = DocumentIngestionService(
        workflow,
        vector_sync=EmptyVectorSync(),
        lifecycle=lifecycle,
    )

    await service.ingest_document(
        _command(source_version=source_version),
        (),
        (),
        resolution_profile="resolve-v1",
        ingestion_run_id="run-60",
        source_hash="hash-2",
    )

    assert workflow.calls[0]["previous_source_versions"] == ()
