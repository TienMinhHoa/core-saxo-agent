from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from saxophone.ingestion.content_ledger import (
    ContentFingerprint,
    ContentReservationStatus,
    SqliteContentLedger,
)
from saxophone.ingestion.models import EmbeddingRecord, IngestionCommand, IngestionSourceChunk
from saxophone.ingestion.progress import IngestionProgressReporter
from saxophone.ingestion.use_cases import DocumentChunkTaggingService, IndexDocument, IngestDocument
from saxophone.platform.observability import InMemoryEventSink
from saxophone.tagging.chunk_models import (
    ChunkParagraphTaggingResult,
    ChunkTaggingLabel,
    ChunkTaggingRequest,
    ChunkTaggingResult,
)
from saxophone.tagging.chunk_service import ChunkTaggingService, ChunkTaggingTransactionService
from saxophone.tagging.models import ContentRole, ParagraphBlock


def _command(
    *,
    document_ref: str = "doc-1",
    source_version: str = "source-v1",
) -> IngestionCommand:
    return IngestionCommand(
        document_ref=document_ref,
        source_version=source_version,
        chunking_profile="chunk-v1",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
    )


def _chunk(
    chunk_id: str,
    *,
    document_ref: str = "doc-1",
    source_version: str = "source-v1",
    text: str = "A repeated musical phrase.",
) -> IngestionSourceChunk:
    return IngestionSourceChunk(
        chunk_id=chunk_id,
        document_ref=document_ref,
        source_version=source_version,
        search_text=text,
        access_scope="tenant-a",
        metadata={"heading": "Repeated phrase"},
    )


def _paragraph(paragraph_id: str, chunk_id: str) -> ParagraphBlock:
    return ParagraphBlock(
        paragraph_id=paragraph_id,
        chunk_id=chunk_id,
        ordinal=0,
        text="A repeated musical phrase.",
    )


def _request(chunk_id: str = "chunk-1", paragraph_id: str = "chunk-1:p1") -> ChunkTaggingRequest:
    from saxophone.tagging.chunk_models import ChunkParagraphTaggingInput

    return ChunkTaggingRequest(
        chunk_id,
        (ChunkParagraphTaggingInput(_paragraph(paragraph_id, chunk_id)),),
    )


def _result(request: ChunkTaggingRequest) -> ChunkTaggingResult:
    return ChunkTaggingResult(
        request.chunk_id,
        ("Musical phrase",),
        (
            ChunkParagraphTaggingResult(
                request.paragraphs[0].paragraph.paragraph_id,
                (
                    ChunkTaggingLabel(
                        "Musical phrase",
                        "create_new",
                        "Musical phrase",
                        (ContentRole.DEFINITION,),
                    ),
                ),
            ),
        ),
    )


def test_content_fingerprint_uses_exact_utf8_bytes() -> None:
    text = "Nhip điệu chính xác\n"
    encoded = text.encode("utf-8")

    fingerprint = ContentFingerprint.from_text(text)

    assert fingerprint.sha256 == hashlib.sha256(encoded).hexdigest()
    assert fingerprint.md5 == hashlib.md5(encoded).hexdigest()
    assert fingerprint.byte_length == len(encoded)
    assert ContentFingerprint.from_text(text + " ") != fingerprint


@pytest.mark.anyio
async def test_sqlite_content_ledger_persists_ready_results_across_instances(tmp_path) -> None:
    database = tmp_path / "ingestion.sqlite3"
    request = _request()
    first = SqliteContentLedger(database)

    reservation = await first.reserve(
        "A repeated musical phrase.",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        request=request,
    )
    assert reservation.status is ContentReservationStatus.RESERVED
    await first.complete(
        reservation,
        request=request,
        result=_result(request),
        embedding=(0.1, 0.2),
    )

    second = SqliteContentLedger(database)
    cached = await second.reserve(
        "A repeated musical phrase.",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        request=_request("other-chunk", "other:p1"),
    )

    assert cached.status is ContentReservationStatus.READY
    assert cached.cached_result is not None
    assert cached.cached_result.chunk_id == "other-chunk"
    assert cached.cached_result.paragraphs[0].paragraph_ref == "other:p1"


@pytest.mark.anyio
async def test_failed_content_reservation_can_be_retried(tmp_path) -> None:
    ledger = SqliteContentLedger(tmp_path / "ingestion.sqlite3")
    request = _request()
    first = await ledger.reserve(
        "A repeated musical phrase.",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        request=request,
    )

    await ledger.fail(first)
    retried = await ledger.reserve(
        "A repeated musical phrase.",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        request=request,
    )

    assert retried.status is ContentReservationStatus.RESERVED
    assert retried.reservation_token != first.reservation_token


@pytest.mark.anyio
async def test_content_ledger_rejects_sha_rows_with_inconsistent_md5_or_length(tmp_path) -> None:
    database = tmp_path / "ingestion.sqlite3"
    ledger = SqliteContentLedger(database)
    request = _request()
    await ledger.reserve(
        "A repeated musical phrase.",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        request=request,
    )
    fingerprint = ContentFingerprint.from_text("A repeated musical phrase.")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE processed_chunk_content SET content_md5 = ? WHERE content_sha256 = ?",
            ("0" * 32, fingerprint.sha256),
        )

    with pytest.raises(ValueError, match="fingerprint collision"):
        await ledger.reserve(
            "A repeated musical phrase.",
            tagging_profile="tag-v1",
            embedding_profile="embed-v1",
            request=request,
        )


@pytest.mark.anyio
async def test_concurrent_duplicate_reservations_choose_one_processor(tmp_path) -> None:
    ledger = SqliteContentLedger(tmp_path / "ingestion.sqlite3")
    request = _request()

    first, second = await asyncio.gather(
        ledger.reserve(
            "A repeated musical phrase.",
            tagging_profile="tag-v1",
            embedding_profile="embed-v1",
            request=request,
        ),
        ledger.reserve(
            "A repeated musical phrase.",
            tagging_profile="tag-v1",
            embedding_profile="embed-v1",
            request=request,
        ),
    )

    assert {first.status, second.status} == {
        ContentReservationStatus.RESERVED,
        ContentReservationStatus.PROCESSING,
    }


@pytest.mark.anyio
async def test_processing_reservation_is_reclaimed_after_sixty_minutes(tmp_path) -> None:
    current_time = [datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)]
    ledger = SqliteContentLedger(
        tmp_path / "ingestion.sqlite3",
        processing_timeout=timedelta(minutes=60),
        clock=lambda: current_time[0],
    )
    request = _request()
    first = await ledger.reserve(
        "A repeated musical phrase.",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        request=request,
    )

    current_time[0] += timedelta(minutes=59, seconds=59)
    active = await ledger.reserve(
        "A repeated musical phrase.",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        request=request,
    )
    current_time[0] += timedelta(seconds=1)
    reclaimed = await ledger.reserve(
        "A repeated musical phrase.",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        request=request,
    )

    assert active.status is ContentReservationStatus.PROCESSING
    assert reclaimed.status is ContentReservationStatus.RESERVED
    assert reclaimed.reservation_token != first.reservation_token
    assert reclaimed.recovered_stale_processing is True


class CountingTagger:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[ChunkTaggingRequest] = []
        self.error = error

    async def tag(self, request: ChunkTaggingRequest) -> ChunkTaggingResult:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return _result(request)


class FailingSecondTagger(CountingTagger):
    async def tag(self, request: ChunkTaggingRequest) -> ChunkTaggingResult:
        self.calls.append(request)
        if len(self.calls) == 2:
            raise RuntimeError("second chunk failed")
        return _result(request)


class CountingEmbeddingProvider:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[tuple[tuple[str, str], ...], str]] = []
        self.error = error

    async def embed(self, chunks, *, source_version: str):
        normalized = tuple(chunks)
        self.calls.append((normalized, source_version))
        if self.error is not None:
            raise self.error
        return tuple(
            EmbeddingRecord(chunk_id, source_version, "embed-v1", (0.1, 0.2))
            for chunk_id, _ in normalized
        )


class RecordingCommitter:
    def __init__(self) -> None:
        self.document_calls: list[dict[str, object]] = []
        self.chunk_calls: list[dict[str, object]] = []

    async def commit_chunk(self, **kwargs: object) -> None:
        self.chunk_calls.append(kwargs)

    async def commit_document(self, **kwargs: object) -> None:
        self.document_calls.append(kwargs)


class RecordingVectorIndex:
    def __init__(self) -> None:
        self.records = ()

    async def upsert_chunks(self, records) -> None:
        self.records = tuple(records)


def _workflow(ledger, tagger, provider, committer, index=None) -> IngestDocument:
    return IngestDocument(
        None,
        IndexDocument(index or RecordingVectorIndex(), provider, ledger),
        chunk_tagging=DocumentChunkTaggingService(
            ChunkTaggingTransactionService(ChunkTaggingService(tagger), committer),
            content_ledger=ledger,
        ),
    )


@pytest.mark.anyio
async def test_duplicate_chunks_in_one_ingest_call_providers_once(tmp_path) -> None:
    ledger = SqliteContentLedger(tmp_path / "ingestion.sqlite3")
    tagger = CountingTagger()
    provider = CountingEmbeddingProvider()
    committer = RecordingCommitter()
    workflow = _workflow(ledger, tagger, provider, committer)
    chunks = (_chunk("chunk-1"), _chunk("chunk-2"))
    paragraphs = (_paragraph("chunk-1:p1", "chunk-1"), _paragraph("chunk-2:p1", "chunk-2"))

    report = await workflow.execute(
        _command(),
        chunks,
        paragraphs,
        resolution_profile="unused",
    )

    assert report.indexed is True
    assert len(tagger.calls) == 1
    assert provider.calls == [((("chunk-1", "A repeated musical phrase."),), "source-v1")]
    assert report.embedded_count == 1
    assert report.reused_embedding_count == 1
    assert report.skipped_count == 1
    assert len(committer.chunk_calls) == 2


@pytest.mark.anyio
async def test_ready_content_reuses_providers_for_another_document_and_keeps_provenance(
    tmp_path,
) -> None:
    ledger = SqliteContentLedger(tmp_path / "ingestion.sqlite3")
    first_index = RecordingVectorIndex()
    first = _workflow(
        ledger,
        CountingTagger(),
        CountingEmbeddingProvider(),
        RecordingCommitter(),
        first_index,
    )
    await first.execute(
        _command(),
        (_chunk("chunk-1"),),
        (_paragraph("chunk-1:p1", "chunk-1"),),
        resolution_profile="unused",
    )

    tagger = CountingTagger(AssertionError("ready content must not call DeepSeek"))
    provider = CountingEmbeddingProvider(AssertionError("ready content must not call OpenAI"))
    committer = RecordingCommitter()
    index = RecordingVectorIndex()
    second = _workflow(ledger, tagger, provider, committer, index)
    command = _command(document_ref="doc-2", source_version="source-v2")
    chunk = _chunk(
        "doc-2-chunk-1",
        document_ref="doc-2",
        source_version="source-v2",
    )
    paragraph = replace(
        _paragraph("doc-2:p1", "doc-2-chunk-1"),
        paragraph_id="doc-2:p1",
    )

    report = await second.execute(
        command,
        (chunk,),
        (paragraph,),
        resolution_profile="unused",
    )

    assert report.indexed is True
    assert report.skipped_count == 1
    assert report.reused_embedding_count == 1
    assert tagger.calls == []
    assert provider.calls == []
    assert index.records[0].document_ref == "doc-2"
    assert index.records[0].chunk_id == "doc-2-chunk-1"
    assert committer.chunk_calls[0]["paragraph_ids"] == ("doc-2:p1",)


@pytest.mark.anyio
async def test_embedding_failure_releases_content_for_retry(tmp_path) -> None:
    ledger = SqliteContentLedger(tmp_path / "ingestion.sqlite3")
    failed = _workflow(
        ledger,
        CountingTagger(),
        CountingEmbeddingProvider(RuntimeError("embedding unavailable")),
        RecordingCommitter(),
    )
    chunk = _chunk("chunk-1")
    paragraph = _paragraph("chunk-1:p1", "chunk-1")

    report = await failed.execute(
        _command(),
        (chunk,),
        (paragraph,),
        resolution_profile="unused",
    )
    retry_tagger = CountingTagger()
    retried = _workflow(
        ledger,
        retry_tagger,
        CountingEmbeddingProvider(),
        RecordingCommitter(),
    )
    retry_report = await retried.execute(
        _command(),
        (chunk,),
        (paragraph,),
        resolution_profile="unused",
    )

    assert report.indexed is False
    assert retry_report.indexed is True
    assert len(retry_tagger.calls) == 1


@pytest.mark.anyio
async def test_tagging_failure_releases_every_reservation_owned_by_the_batch(tmp_path) -> None:
    ledger = SqliteContentLedger(tmp_path / "ingestion.sqlite3")
    service = DocumentChunkTaggingService(
        ChunkTaggingTransactionService(
            ChunkTaggingService(FailingSecondTagger()),
            RecordingCommitter(),
        ),
        content_ledger=ledger,
    )
    chunks = (
        _chunk("chunk-1", text="First unique chunk."),
        _chunk("chunk-2", text="Second unique chunk."),
    )
    paragraphs = (
        _paragraph("chunk-1:p1", "chunk-1"),
        _paragraph("chunk-2:p1", "chunk-2"),
    )

    with pytest.raises(RuntimeError, match="second chunk failed"):
        await service.prepare(_command(), chunks, paragraphs)

    requests = tuple(
        _request(chunk.chunk_id, paragraph.paragraph_id)
        for chunk, paragraph in zip(chunks, paragraphs)
    )
    retries = [
        await ledger.reserve(
            chunk.search_text,
            tagging_profile="tag-v1",
            embedding_profile="embed-v1",
            request=request,
        )
        for chunk, request in zip(chunks, requests)
    ]
    assert [reservation.status for reservation in retries] == [
        ContentReservationStatus.RESERVED,
        ContentReservationStatus.RESERVED,
    ]


@pytest.mark.anyio
async def test_tagging_cancellation_releases_the_current_reservation(tmp_path) -> None:
    ledger = SqliteContentLedger(tmp_path / "ingestion.sqlite3")
    service = DocumentChunkTaggingService(
        ChunkTaggingTransactionService(
            ChunkTaggingService(CountingTagger(asyncio.CancelledError())),
            RecordingCommitter(),
        ),
        content_ledger=ledger,
    )
    chunk = _chunk("chunk-1")
    paragraph = _paragraph("chunk-1:p1", "chunk-1")

    with pytest.raises(asyncio.CancelledError):
        await service.prepare(_command(), (chunk,), (paragraph,))

    retried = await ledger.reserve(
        chunk.search_text,
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        request=_request(),
    )
    assert retried.status is ContentReservationStatus.RESERVED


@pytest.mark.anyio
async def test_active_processing_chunk_is_warned_skipped_and_does_not_block_later_chunks(
    tmp_path,
) -> None:
    ledger = SqliteContentLedger(tmp_path / "ingestion.sqlite3")
    chunks = (
        _chunk("chunk-1", text="First unique chunk."),
        _chunk("chunk-2", text="Second unique chunk."),
    )
    paragraphs = (
        _paragraph("chunk-1:p1", "chunk-1"),
        _paragraph("chunk-2:p1", "chunk-2"),
    )
    await ledger.reserve(
        chunks[0].search_text,
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        request=_request("chunk-1", "chunk-1:p1"),
    )
    tagger = CountingTagger()
    service = DocumentChunkTaggingService(
        ChunkTaggingTransactionService(
            ChunkTaggingService(tagger),
            RecordingCommitter(),
        ),
        content_ledger=ledger,
    )
    sink = InMemoryEventSink()
    progress = IngestionProgressReporter(
        sink,
        ingestion_run_id="run-1",
        document_ref="doc-1",
        total_chunks=2,
        clock=lambda: 10.0,
    )

    prepared = await service.prepare(
        _command(),
        chunks,
        paragraphs,
        progress=progress,
    )

    assert prepared.skipped_chunk_ids == ("chunk-1",)
    assert [request.chunk_id for request in prepared.requests] == ["chunk-2"]
    assert [request.chunk_id for request in tagger.calls] == ["chunk-2"]
    warning = next(event for event in sink.events if event.result == "warning")
    assert warning.chunk_id == "chunk-1"
    assert warning.reason_code == "chunk_content_already_processing"
    await service.fail(prepared)


@pytest.mark.anyio
async def test_ingestion_with_active_processing_chunk_returns_warning_without_partial_commit(
    tmp_path,
) -> None:
    ledger = SqliteContentLedger(tmp_path / "ingestion.sqlite3")
    chunks = (
        _chunk("chunk-1", text="First unique chunk."),
        _chunk("chunk-2", text="Second unique chunk."),
    )
    paragraphs = (
        _paragraph("chunk-1:p1", "chunk-1"),
        _paragraph("chunk-2:p1", "chunk-2"),
    )
    await ledger.reserve(
        chunks[0].search_text,
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        request=_request("chunk-1", "chunk-1:p1"),
    )
    tagger = CountingTagger()
    provider = CountingEmbeddingProvider()
    committer = RecordingCommitter()

    report = await _workflow(ledger, tagger, provider, committer).execute(
        _command(),
        chunks,
        paragraphs,
        resolution_profile="unused",
    )

    assert report.indexed is False
    assert report.errors == ()
    assert report.skipped_count == 1
    assert report.warnings == ("skipped 1 chunk(s) already being processed",)
    assert provider.calls == []
    assert committer.chunk_calls == []
