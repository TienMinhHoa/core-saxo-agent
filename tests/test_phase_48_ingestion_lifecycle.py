from __future__ import annotations

import asyncio

import pytest

from saxophone.ingestion.models import IngestionCommand, IngestionReport
from saxophone.ingestion.services import DocumentIngestionService
from saxophone.ingestion.state import IngestionStatus, SqliteIngestionStateRepository
from saxophone.ingestion.vector_sync import VectorSyncService
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository


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


def _report(*, indexed: bool = True) -> IngestionReport:
    return IngestionReport(
        document_ref="doc-1",
        source_version="v1",
        chunk_count=1,
        paragraph_count=1,
        tagged_paragraph_count=1,
        failed_paragraph_count=0 if indexed else 1,
        embedded_count=1 if indexed else 0,
        reused_embedding_count=0,
        skipped_count=0,
        index_version="index-v1",
        indexed=indexed,
        warnings=(),
        errors=() if indexed else ("workflow failed",),
    )


class FakeWorkflow:
    def __init__(self, report: IngestionReport) -> None:
        self.report = report

    async def execute(self, command, chunks, paragraphs, *, resolution_profile):
        return self.report


class FakeLifecycle:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def start_or_resume(self, **kwargs):
        self.calls.append(("start_or_resume", (), kwargs))

    async def mark_tagged_pending_vector_sync(self, ingestion_run_id):
        self.calls.append(("mark_tagged_pending_vector_sync", (ingestion_run_id,), {}))

    async def mark_ready(self, ingestion_run_id, *, pending_event_count=0):
        self.calls.append(
            ("mark_ready", (ingestion_run_id,), {"pending_event_count": pending_event_count})
        )

    async def mark_failed(self, ingestion_run_id, *, error_code):
        self.calls.append(("mark_failed", (ingestion_run_id,), {"error_code": error_code}))


class FakeVectorSync:
    def __init__(self, result: dict[str, int], pending: int = 0) -> None:
        self.result = result
        self.pending = pending
        self.calls: list[tuple[str, int]] = []
        self.pending_calls: list[str] = []

    async def sync_pending(self, *, ingestion_run_id: str, limit: int):
        self.calls.append((ingestion_run_id, limit))
        return self.result

    async def pending_count(self, *, ingestion_run_id: str) -> int:
        self.pending_calls.append(ingestion_run_id)
        return self.pending


class FakeExporter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def export(self, **kwargs):
        self.calls.append(kwargs)


class EmptyVectorIndex:
    async def upsert_chunks(self, records):
        raise AssertionError("no events should be upserted")

    async def delete_chunks(self, chunk_ids):
        raise AssertionError("no events should be deleted")

    async def upsert_concepts(self, records):
        raise AssertionError("no events should be upserted")

    async def delete_concepts(self, record_ids):
        raise AssertionError("no events should be deleted")


@pytest.mark.anyio
async def test_lifecycle_ingestion_scopes_sync_and_marks_ready() -> None:
    lifecycle = FakeLifecycle()
    sync = FakeVectorSync({"succeeded": 2, "failed": 0})
    exporter = FakeExporter()
    service = DocumentIngestionService(
        FakeWorkflow(_report()),
        vector_sync=sync,
        lifecycle=lifecycle,
        artifact_exporter=exporter,
    )

    result = await service.ingest_document(
        _command(),
        ("chunk",),
        ("paragraph",),
        resolution_profile="resolve-v1",
        sync_limit=7,
        ingestion_run_id="run-1",
        source_hash="hash-1",
    )

    assert result.indexed is True
    assert sync.calls == [("run-1", 7)]
    assert sync.pending_calls == ["run-1"]
    assert [call[0] for call in lifecycle.calls] == [
        "start_or_resume",
        "mark_tagged_pending_vector_sync",
        "mark_ready",
    ]
    assert lifecycle.calls[0][2] == {
        "ingestion_run_id": "run-1",
        "document_ref": "doc-1",
        "source_version": "v1",
        "source_hash": "hash-1",
    }
    assert lifecycle.calls[2][2] == {"pending_event_count": 0}
    assert len(exporter.calls) == 1


@pytest.mark.anyio
async def test_lifecycle_ingestion_persists_ready_state_with_real_coordinators(tmp_path) -> None:
    lifecycle = SqliteIngestionStateRepository(tmp_path / "state.sqlite")
    outbox = SqliteVectorOutboxRepository(tmp_path / "outbox.sqlite")
    sync = VectorSyncService(outbox, EmptyVectorIndex())
    service = DocumentIngestionService(
        FakeWorkflow(_report()), vector_sync=sync, lifecycle=lifecycle
    )

    result = await service.ingest_document(
        _command(), (), (), resolution_profile="resolve-v1", ingestion_run_id="run-1", source_hash="hash-1"
    )

    run = await lifecycle.get_run("run-1")
    document = await lifecycle.get_document("doc-1")
    assert result.indexed is True
    assert run.status is IngestionStatus.READY
    assert document.status is IngestionStatus.READY
    assert document.active_version == "v1"


@pytest.mark.anyio
async def test_lifecycle_ingestion_keeps_run_pending_when_sync_is_incomplete() -> None:
    lifecycle = FakeLifecycle()
    sync = FakeVectorSync({"succeeded": 1, "failed": 0}, pending=2)
    service = DocumentIngestionService(
        FakeWorkflow(_report()), vector_sync=sync, lifecycle=lifecycle
    )

    result = await service.ingest_document(
        _command(), (), (), resolution_profile="resolve-v1", ingestion_run_id="run-1", source_hash="hash-1"
    )

    assert result.indexed is False
    assert result.vector_sync_failed == 0
    assert result.errors == ("vector sync pending for 2 event(s)",)
    assert [call[0] for call in lifecycle.calls] == [
        "start_or_resume",
        "mark_tagged_pending_vector_sync",
    ]


@pytest.mark.anyio
async def test_lifecycle_ingestion_marks_failed_without_export_on_sync_error() -> None:
    lifecycle = FakeLifecycle()
    sync = FakeVectorSync({"succeeded": 0, "failed": 2})
    exporter = FakeExporter()
    service = DocumentIngestionService(
        FakeWorkflow(_report()),
        vector_sync=sync,
        lifecycle=lifecycle,
        artifact_exporter=exporter,
    )

    result = await service.ingest_document(
        _command(), (), (), resolution_profile="resolve-v1", ingestion_run_id="run-1", source_hash="hash-1"
    )

    assert result.indexed is False
    assert result.vector_sync_failed == 2
    assert [call[0] for call in lifecycle.calls] == [
        "start_or_resume",
        "mark_tagged_pending_vector_sync",
        "mark_failed",
    ]
    assert lifecycle.calls[-1][2] == {"error_code": "vector_sync_failed"}
    assert exporter.calls == []


@pytest.mark.anyio
async def test_lifecycle_ingestion_marks_failed_when_sync_report_is_malformed() -> None:
    lifecycle = FakeLifecycle()
    sync = FakeVectorSync({"succeeded": 1, "failed": -1})
    service = DocumentIngestionService(
        FakeWorkflow(_report()), vector_sync=sync, lifecycle=lifecycle
    )

    with pytest.raises(ValueError, match="failed count"):
        await service.ingest_document(
            _command(),
            (),
            (),
            resolution_profile="resolve-v1",
            ingestion_run_id="run-1",
            source_hash="hash-1",
        )

    assert lifecycle.calls[-1][2] == {"error_code": "vector_sync_error"}


@pytest.mark.anyio
async def test_lifecycle_ingestion_marks_failed_when_workflow_report_is_not_indexed() -> None:
    lifecycle = FakeLifecycle()
    sync = FakeVectorSync({"succeeded": 0, "failed": 0})
    service = DocumentIngestionService(
        FakeWorkflow(_report(indexed=False)), vector_sync=sync, lifecycle=lifecycle
    )

    result = await service.ingest_document(
        _command(), (), (), resolution_profile="resolve-v1", ingestion_run_id="run-1", source_hash="hash-1"
    )

    assert result.indexed is False
    assert sync.calls == []
    assert [call[0] for call in lifecycle.calls] == ["start_or_resume", "mark_failed"]
    assert lifecycle.calls[-1][2] == {"error_code": "ingestion_failed"}


def test_lifecycle_requires_run_identity_and_vector_sync() -> None:
    lifecycle = FakeLifecycle()

    with pytest.raises(TypeError, match="vector sync"):
        DocumentIngestionService(FakeWorkflow(_report()), lifecycle=lifecycle)

    service = DocumentIngestionService(
        FakeWorkflow(_report()), vector_sync=FakeVectorSync({"succeeded": 0, "failed": 0}), lifecycle=lifecycle
    )

    with pytest.raises(ValueError, match="ingestion_run_id"):
        asyncio.run(
            service.ingest_document(
                _command(),
                (),
                (),
                resolution_profile="resolve-v1",
                source_hash="hash-1",
            )
        )
