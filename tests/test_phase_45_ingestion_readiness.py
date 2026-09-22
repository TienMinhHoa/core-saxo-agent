from __future__ import annotations

import pytest

from saxophone.ingestion.models import IngestionCommand, IngestionReport
from saxophone.ingestion.services import DocumentIngestionService


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


def _report() -> IngestionReport:
    return IngestionReport(
        document_ref="doc-1",
        source_version="v1",
        chunk_count=1,
        paragraph_count=1,
        tagged_paragraph_count=1,
        failed_paragraph_count=0,
        embedded_count=1,
        reused_embedding_count=0,
        skipped_count=0,
        index_version="index-v1",
        indexed=True,
        warnings=(),
        errors=(),
    )


class FakeWorkflow:
    async def execute(self, command, chunks, paragraphs, *, resolution_profile):
        return _report()


class FakeVectorSync:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[int] = []

    async def sync_pending(self, *, limit: int):
        self.calls.append(limit)
        return self.result


class FakeExporter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def export(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


@pytest.mark.anyio
async def test_vector_sync_failure_keeps_document_unready_and_skips_exports() -> None:
    sync = FakeVectorSync({"succeeded": 1, "failed": 2})
    exporter = FakeExporter()
    service = DocumentIngestionService(
        FakeWorkflow(), vector_sync=sync, artifact_exporter=exporter
    )

    result = await service.ingest_document(
        _command(), (), (), resolution_profile="resolve-v1"
    )

    assert result.indexed is False
    assert result.vector_sync_failed == 2
    assert result.errors == ("vector sync failed for 2 event(s)",)
    assert sync.calls == [100]
    assert exporter.calls == []


@pytest.mark.anyio
async def test_vector_sync_report_must_contain_non_negative_integer_counts() -> None:
    sync = FakeVectorSync({"succeeded": 1, "failed": -1})
    service = DocumentIngestionService(FakeWorkflow(), vector_sync=sync)

    with pytest.raises(ValueError, match="failed count"):
        await service.ingest_document(
            _command(), (), (), resolution_profile="resolve-v1"
        )
