from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO

import pytest

from saxophone.ingestion.models import (
    IngestionCommand,
    IngestionReport,
    IngestionSourceChunk,
)
from saxophone.ingestion.progress import IngestionProgressReporter
from saxophone.ingestion.services import DocumentIngestionService
from saxophone.ingestion.use_cases import DocumentChunkTaggingService
from saxophone.platform.observability import DailyTextFileEventSink, InMemoryEventSink
from saxophone.tagging.chunk_models import (
    ChunkParagraphTaggingResult,
    ChunkTaggingResult,
)
from saxophone.tagging.chunk_service import ChunkTaggingService, ChunkTaggingTransactionService
from saxophone.tagging.models import ParagraphBlock


def test_progress_reporter_emits_chunk_counts_percentage_elapsed_and_eta() -> None:
    sink = InMemoryEventSink()
    times = iter((100.0, 110.0, 130.0))
    reporter = IngestionProgressReporter(
        sink,
        ingestion_run_id="music-theory-full-source123",
        document_ref="music-theory-full",
        total_chunks=4,
        clock=lambda: next(times),
    )

    reporter.started()
    reporter.chunk_completed("chunk-1", completed_chunks=1, reused=False)
    reporter.chunk_completed("chunk-2", completed_chunks=2, reused=True)

    started, first, second = sink.events
    assert started.stage == "starting"
    assert started.completed_count == 0
    assert started.total_count == 4
    assert started.progress_percent == 0.0
    assert started.eta_seconds is None
    assert first.stage == "tagging"
    assert first.chunk_id == "chunk-1"
    assert first.completed_count == 1
    assert first.progress_percent == 25.0
    assert first.elapsed_seconds == 10.0
    assert first.eta_seconds == 30.0
    assert first.result == "completed"
    assert second.chunk_id == "chunk-2"
    assert second.completed_count == 2
    assert second.progress_percent == 50.0
    assert second.elapsed_seconds == 30.0
    assert second.eta_seconds == 30.0
    assert second.result == "reused"


def test_progress_reporter_emits_stage_and_terminal_completion() -> None:
    sink = InMemoryEventSink()
    times = iter((5.0, 7.5, 9.0))
    reporter = IngestionProgressReporter(
        sink,
        ingestion_run_id="run-1",
        document_ref="doc-1",
        total_chunks=2,
        clock=lambda: next(times),
    )

    reporter.stage_started("embedding", completed_chunks=2)
    reporter.completed()

    stage, completed = sink.events
    assert stage.stage == "embedding"
    assert stage.result == "started"
    assert stage.progress_percent == 100.0
    assert completed.stage == "completed"
    assert completed.result == "success"
    assert completed.progress_percent == 100.0


def test_daily_sink_writes_and_echoes_human_readable_ingestion_progress(tmp_path) -> None:
    console = StringIO()
    sink = DailyTextFileEventSink(
        tmp_path,
        clock=lambda: datetime(2026, 9, 23, 21, 30, tzinfo=timezone.utc),
        progress_stream=console,
    )
    reporter = IngestionProgressReporter(
        sink,
        ingestion_run_id="run-1",
        document_ref="music-theory-full",
        total_chunks=10,
        clock=lambda: 100.0,
    )

    reporter.chunk_completed("chunk-3", completed_chunks=3, reused=False)

    content = (tmp_path / "2026-09-23.log").read_text(encoding="utf-8")
    assert "event=ingestion.progress" in content
    assert "document_ref=music-theory-full" in content
    assert "stage=tagging" in content
    assert "chunk_id=chunk-3" in content
    assert "completed=3" in content
    assert "total=10" in content
    assert "progress_percent=30.00" in content
    assert "[INGEST]" in console.getvalue()
    assert "chunk=3/10" in console.getvalue()
    assert "30.00%" in console.getvalue()


class _Tagger:
    async def tag(self, request):
        return ChunkTaggingResult(
            request.chunk_id,
            (),
            tuple(
                ChunkParagraphTaggingResult(item.paragraph.paragraph_id, ())
                for item in request.paragraphs
            ),
        )


class _TransactionRepository:
    async def commit_chunk(self, **_kwargs) -> None:
        return None

    async def commit_document(self, **_kwargs) -> None:
        return None


@pytest.mark.anyio
async def test_chunk_tagging_reports_the_current_chunk_and_completed_count() -> None:
    sink = InMemoryEventSink()
    reporter = IngestionProgressReporter(
        sink,
        ingestion_run_id="run-1",
        document_ref="doc-1",
        total_chunks=2,
        clock=lambda: 10.0,
    )
    service = DocumentChunkTaggingService(
        ChunkTaggingTransactionService(
            ChunkTaggingService(_Tagger()),
            _TransactionRepository(),
        )
    )
    command = _command()
    chunks = (
        IngestionSourceChunk("chunk-1", "doc-1", "v1", "First", "default", {}),
        IngestionSourceChunk("chunk-2", "doc-1", "v1", "Second", "default", {}),
    )
    paragraphs = (
        ParagraphBlock("p-1", "chunk-1", 0, "First"),
        ParagraphBlock("p-2", "chunk-2", 0, "Second"),
    )

    await service.prepare(command, chunks, paragraphs, progress=reporter)

    progress = [event for event in sink.events if event.stage == "tagging"]
    assert [(event.result, event.current_count, event.completed_count) for event in progress] == [
        ("started", 1, 0),
        ("completed", 1, 1),
        ("started", 2, 1),
        ("completed", 2, 2),
    ]


class _Workflow:
    def __init__(self) -> None:
        self.progress = None

    async def execute(self, command, chunks, paragraphs, *, resolution_profile, progress=None):
        self.progress = progress
        progress.stage_started("embedding", completed_chunks=len(chunks))
        return IngestionReport(
            document_ref=command.document_ref,
            source_version=command.source_version,
            chunk_count=len(chunks),
            paragraph_count=len(paragraphs),
            tagged_paragraph_count=len(paragraphs),
            failed_paragraph_count=0,
            embedded_count=len(chunks),
            reused_embedding_count=0,
            skipped_count=0,
            index_version=command.index_profile,
            indexed=True,
            warnings=(),
            errors=(),
        )


@pytest.mark.anyio
async def test_document_ingestion_owns_progress_lifecycle() -> None:
    sink = InMemoryEventSink()
    workflow = _Workflow()
    service = DocumentIngestionService(workflow, event_sink=sink)
    chunks = (object(), object())
    paragraphs = (object(),)

    report = await service.ingest_document(
        _command(),
        chunks,
        paragraphs,
        resolution_profile="topic-v1",
    )

    assert report.indexed is True
    assert isinstance(workflow.progress, IngestionProgressReporter)
    assert [event.stage for event in sink.events] == ["starting", "embedding", "completed"]


def _command() -> IngestionCommand:
    return IngestionCommand(
        document_ref="doc-1",
        source_version="v1",
        chunking_profile="header-json-v1",
        tagging_profile="topic-v1",
        embedding_profile="embedding-v1",
        index_profile="topic-index-v1",
        access_scope="default",
    )
