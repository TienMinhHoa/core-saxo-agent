from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from saxophone.ingestion.content_ledger import SqliteContentLedger
from saxophone.ingestion.models import EmbeddingRecord, IngestionCommand, IngestionSourceChunk
from saxophone.ingestion.services import DocumentIngestionService
from saxophone.ingestion.state import IngestionStatus, SqliteIngestionStateRepository
from saxophone.ingestion.transaction import SqliteIngestionTransactionRepository
from saxophone.ingestion.use_cases import DocumentChunkTaggingService, IndexDocument, IngestDocument
from saxophone.ingestion.vector_state import SqliteVectorIndexStateRepository
from saxophone.ingestion.vector_sync import VectorSyncService
from saxophone.tagging.chunk_models import (
    ChunkParagraphTaggingResult,
    ChunkTaggingLabel,
    ChunkTaggingRequest,
    ChunkTaggingResult,
)
from saxophone.tagging.chunk_service import ChunkTaggingService, ChunkTaggingTransactionService
from saxophone.tagging.models import ContentRole, ParagraphBlock
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository


def _command() -> IngestionCommand:
    return IngestionCommand(
        document_ref="checkpoint-document",
        source_version="source-v1",
        chunking_profile="chunk-v1",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
    )


def _chunk(index: int) -> IngestionSourceChunk:
    return IngestionSourceChunk(
        chunk_id=f"chunk-{index}",
        document_ref="checkpoint-document",
        source_version="source-v1",
        search_text=f"Unique music content {index}.",
        access_scope="tenant-a",
        metadata={"heading": f"Section {index}"},
    )


def _paragraph(index: int) -> ParagraphBlock:
    return ParagraphBlock(
        paragraph_id=f"paragraph-{index}",
        chunk_id=f"chunk-{index}",
        ordinal=0,
        text=f"Unique music content {index}.",
    )


def _result(request: ChunkTaggingRequest) -> ChunkTaggingResult:
    return ChunkTaggingResult(
        request.chunk_id,
        ("Music concept",),
        (
            ChunkParagraphTaggingResult(
                request.paragraphs[0].paragraph.paragraph_id,
                (
                    ChunkTaggingLabel(
                        "Music concept",
                        "create_new",
                        "Music concept",
                        (ContentRole.DEFINITION,),
                    ),
                ),
            ),
        ),
    )


class _FailingSecondTagger:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def tag(self, request: ChunkTaggingRequest) -> ChunkTaggingResult:
        self.calls.append(request.chunk_id)
        if len(self.calls) == 2:
            raise RuntimeError("second chunk failed")
        return _result(request)


class _CountingTagger:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def tag(self, request: ChunkTaggingRequest) -> ChunkTaggingResult:
        self.calls.append(request.chunk_id)
        return _result(request)


class _EmbeddingProvider:
    async def embed(self, chunks, *, source_version: str):
        return tuple(
            EmbeddingRecord(chunk_id, source_version, "embed-v1", (0.1, 0.2))
            for chunk_id, _ in chunks
        )


class _VectorIndex:
    def __init__(self) -> None:
        self.records: dict[str, object] = {}

    async def list_chunk_ids(self, *, document_ref: str):
        return tuple(self.records)

    async def upsert_chunks(self, records) -> None:
        for record in records:
            self.records[record.chunk_id] = record

    async def delete_chunks(self, chunk_ids) -> None:
        for chunk_id in chunk_ids:
            self.records.pop(chunk_id, None)


class _FlakyVectorIndex(_VectorIndex):
    def __init__(self) -> None:
        super().__init__()
        self.failures_remaining = 1

    async def upsert_chunks(self, records) -> None:
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("Chroma temporarily unavailable")
        await super().upsert_chunks(records)


def _service(
    database: Path,
    *,
    tagger: object,
    vector_index: _VectorIndex,
) -> DocumentIngestionService:
    ledger = SqliteContentLedger(database)
    transaction = SqliteIngestionTransactionRepository(database)
    vector_state = SqliteVectorIndexStateRepository(database)
    workflow = IngestDocument(
        None,
        IndexDocument(vector_index, _EmbeddingProvider(), ledger),
        chunk_tagging=DocumentChunkTaggingService(
            ChunkTaggingTransactionService(
                ChunkTaggingService(tagger),
                transaction,
            ),
            content_ledger=ledger,
        ),
        vector_state=vector_state,
    )
    return DocumentIngestionService(
        workflow,
        vector_sync=VectorSyncService(
            SqliteVectorOutboxRepository(database),
            vector_index,
            state=vector_state,
        ),
        lifecycle=SqliteIngestionStateRepository(database),
    )


@pytest.mark.anyio
async def test_completed_chunk_is_durable_when_the_next_chunk_fails(tmp_path: Path) -> None:
    database = tmp_path / "ingestion.sqlite3"
    vectors = _VectorIndex()
    service = _service(database, tagger=_FailingSecondTagger(), vector_index=vectors)
    chunks = (_chunk(1), _chunk(2))
    paragraphs = (_paragraph(1), _paragraph(2))

    with pytest.raises(RuntimeError, match="second chunk failed"):
        await service.ingest_document(
            _command(),
            chunks,
            paragraphs,
            resolution_profile="topic-v1",
            ingestion_run_id="checkpoint-run",
            source_hash="source-hash",
        )

    with sqlite3.connect(database) as connection:
        stored_chunks = connection.execute(
            "SELECT chunk_id FROM source_chunks ORDER BY chunk_id"
        ).fetchall()
        ledger_states = connection.execute(
            "SELECT status, COUNT(*) FROM processed_chunk_content GROUP BY status"
        ).fetchall()
        succeeded_events = connection.execute(
            "SELECT record_id FROM vector_outbox WHERE status = 'succeeded'"
        ).fetchall()

    run = await SqliteIngestionStateRepository(database).get_run("checkpoint-run")
    assert stored_chunks == [("chunk-1",)]
    assert ledger_states == [("failed", 1), ("ready", 1)]
    assert succeeded_events == [("chunk-1",)]
    assert tuple(vectors.records) == ("chunk-1",)
    assert run.status is IngestionStatus.FAILED


@pytest.mark.anyio
async def test_retry_reuses_checkpointed_chunk_and_only_processes_the_remainder(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ingestion.sqlite3"
    vectors = _VectorIndex()
    chunks = (_chunk(1), _chunk(2))
    paragraphs = (_paragraph(1), _paragraph(2))
    first = _service(database, tagger=_FailingSecondTagger(), vector_index=vectors)
    with pytest.raises(RuntimeError, match="second chunk failed"):
        await first.ingest_document(
            _command(),
            chunks,
            paragraphs,
            resolution_profile="topic-v1",
            ingestion_run_id="checkpoint-run",
            source_hash="source-hash",
        )

    retry_tagger = _CountingTagger()
    report = await _service(
        database,
        tagger=retry_tagger,
        vector_index=vectors,
    ).ingest_document(
        _command(),
        chunks,
        paragraphs,
        resolution_profile="topic-v1",
        ingestion_run_id="checkpoint-run",
        source_hash="source-hash",
    )

    with sqlite3.connect(database) as connection:
        stored_chunks = connection.execute(
            "SELECT chunk_id FROM source_chunks ORDER BY chunk_id"
        ).fetchall()
        ready_count = connection.execute(
            "SELECT COUNT(*) FROM processed_chunk_content WHERE status = 'ready'"
        ).fetchone()[0]

    run = await SqliteIngestionStateRepository(database).get_run("checkpoint-run")
    assert report.indexed is True
    assert retry_tagger.calls == ["chunk-2"]
    assert stored_chunks == [("chunk-1",), ("chunk-2",)]
    assert ready_count == 2
    assert tuple(vectors.records) == ("chunk-1", "chunk-2")
    assert run.status is IngestionStatus.READY


@pytest.mark.anyio
async def test_failed_vector_checkpoint_is_retried_without_retagging(tmp_path: Path) -> None:
    database = tmp_path / "ingestion.sqlite3"
    vectors = _FlakyVectorIndex()
    first_tagger = _CountingTagger()
    chunk = _chunk(1)
    paragraph = _paragraph(1)

    with pytest.raises(RuntimeError, match="vector sync failed"):
        await _service(
            database,
            tagger=first_tagger,
            vector_index=vectors,
        ).ingest_document(
            _command(),
            (chunk,),
            (paragraph,),
            resolution_profile="topic-v1",
            ingestion_run_id="checkpoint-run",
            source_hash="source-hash",
        )

    retry_tagger = _CountingTagger()
    report = await _service(
        database,
        tagger=retry_tagger,
        vector_index=vectors,
    ).ingest_document(
        _command(),
        (chunk,),
        (paragraph,),
        resolution_profile="topic-v1",
        ingestion_run_id="checkpoint-run",
        source_hash="source-hash",
    )

    assert first_tagger.calls == ["chunk-1"]
    assert retry_tagger.calls == []
    assert report.indexed is True
    assert tuple(vectors.records) == ("chunk-1",)
