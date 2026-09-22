from __future__ import annotations

import pytest

from saxophone.ingestion.models import IngestionCommand, IngestionReport
from saxophone.ingestion.services import DocumentIngestionService
from saxophone.tagging.models import ContentRole, ParagraphConceptRole


def _command() -> IngestionCommand:
    return IngestionCommand(
        document_ref="doc-1",
        source_version="v1",
        chunking_profile="chunk-v1",
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
        tagged_paragraph_count=1 if indexed else 0,
        failed_paragraph_count=0 if indexed else 1,
        embedded_count=1 if indexed else 0,
        reused_embedding_count=0,
        skipped_count=0,
        index_version="index-v1",
        indexed=indexed,
        warnings=(),
        errors=() if indexed else ("failed",),
    )


class FakeWorkflow:
    def __init__(self, report: IngestionReport) -> None:
        self.report = report

    async def execute(self, command, chunks, paragraphs, *, resolution_profile):
        return self.report


class FakeExporter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def export(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


@pytest.mark.anyio
async def test_ingestion_exports_artifacts_after_index_success() -> None:
    exporter = FakeExporter()
    relation = ParagraphConceptRole("p-1", "Harmony", ContentRole.DEFINITION)
    service = DocumentIngestionService(FakeWorkflow(_report()), artifact_exporter=exporter)

    result = await service.ingest_document(
        _command(), ("chunk",), ("paragraph",), resolution_profile="resolve-v1", relations=(relation,)
    )

    assert result.indexed is True
    assert exporter.calls == [
        {
            "document_ref": "doc-1",
            "source_version": "v1",
            "paragraphs": ("paragraph",),
            "relations": (relation,),
            "ingestion_report": result,
        }
    ]


@pytest.mark.anyio
async def test_ingestion_does_not_export_artifacts_after_failure() -> None:
    exporter = FakeExporter()
    service = DocumentIngestionService(FakeWorkflow(_report(indexed=False)), artifact_exporter=exporter)

    result = await service.ingest_document(
        _command(), (), (), resolution_profile="resolve-v1"
    )

    assert result.indexed is False
    assert exporter.calls == []
