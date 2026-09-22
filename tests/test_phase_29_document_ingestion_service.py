from __future__ import annotations

import pytest

from saxophone.ingestion.models import IngestionCommand, IngestionReport
from saxophone.ingestion.services import DocumentIngestionService


def _command() -> IngestionCommand:
    return IngestionCommand(
        document_ref="doc-1",
        source_version="v1",
        chunking_profile="header-v1",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
    )


def _report(indexed: bool = True) -> IngestionReport:
    return IngestionReport(
        document_ref="doc-1",
        source_version="v1",
        chunk_count=1,
        paragraph_count=1,
        tagged_paragraph_count=1,
        failed_paragraph_count=0 if indexed else 1,
        embedded_count=1,
        reused_embedding_count=0,
        skipped_count=0,
        index_version="index-v1",
        indexed=indexed,
        warnings=(),
        errors=() if indexed else ("failed",),
    )


class FakeIngestWorkflow:
    def __init__(self, report: IngestionReport) -> None:
        self.report = report
        self.calls: list[tuple[object, object, object, str]] = []

    async def execute(self, command, chunks, paragraphs, *, resolution_profile):
        self.calls.append((command, chunks, paragraphs, resolution_profile))
        return self.report


class FakeVectorSync:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def sync_pending(self, *, limit: int):
        self.calls.append(limit)
        return {"succeeded": 1, "failed": 0}


@pytest.mark.anyio
async def test_document_ingestion_service_delegates_and_syncs_after_success() -> None:
    workflow = FakeIngestWorkflow(_report())
    sync = FakeVectorSync()
    service = DocumentIngestionService(workflow, vector_sync=sync)

    result = await service.ingest_document(
        _command(), ("chunk",), ("paragraph",), resolution_profile="resolve-v1", sync_limit=7
    )

    assert result is workflow.report
    assert workflow.calls == [(_command(), ("chunk",), ("paragraph",), "resolve-v1")]
    assert sync.calls == [7]


@pytest.mark.anyio
async def test_document_ingestion_service_does_not_sync_failed_ingestion() -> None:
    workflow = FakeIngestWorkflow(_report(indexed=False))
    sync = FakeVectorSync()
    service = DocumentIngestionService(workflow, vector_sync=sync)

    result = await service.ingest_document(
        _command(), (), (), resolution_profile="resolve-v1"
    )

    assert result.indexed is False
    assert sync.calls == []


def test_document_ingestion_service_requires_ingestion_workflow() -> None:
    with pytest.raises(TypeError, match="ingest workflow"):
        DocumentIngestionService(object())
