from __future__ import annotations

import asyncio

import pytest

from saxophone.ingestion.models import EmbeddingRecord, IngestionCommand, IngestionSourceChunk
from saxophone.ingestion.models import IngestionReport
from saxophone.ingestion.services import DocumentIngestionService
from saxophone.ingestion.transaction import SqliteIngestionTransactionRepository
from saxophone.ingestion.use_cases import (
    DocumentChunkTaggingService,
    IndexDocument,
    IngestDocument,
)
from saxophone.ingestion.vector_sync import VectorSyncService
from saxophone.tagging.chunk_models import (
    ChunkParagraphTaggingResult,
    ChunkTaggingLabel,
    ChunkTaggingRequest,
    ChunkTaggingResult,
)
from saxophone.tagging.chunk_service import ChunkTaggingService, ChunkTaggingTransactionService
from saxophone.tagging.models import ContentRole, ParagraphBlock
from saxophone.tagging.sqlite_repository import SqliteTaggingRepository
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository


def _command() -> IngestionCommand:
    return IngestionCommand(
        document_ref="doc-1",
        source_version="source-v1",
        chunking_profile="chunk-v1",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
    )


def _chunk() -> IngestionSourceChunk:
    return IngestionSourceChunk(
        chunk_id="chunk-1",
        document_ref="doc-1",
        source_version="source-v1",
        search_text="Harmony combines notes.",
        access_scope="tenant-a",
        metadata={"heading": "Harmony"},
    )


def _paragraph() -> ParagraphBlock:
    return ParagraphBlock(
        paragraph_id="chunk-1:p1",
        chunk_id="chunk-1",
        ordinal=0,
        text="Harmony combines notes.",
    )


class FakeChunkTagger:
    async def tag(self, request: ChunkTaggingRequest) -> ChunkTaggingResult:
        return ChunkTaggingResult(
            request.chunk_id,
            ("Harmony",),
            (
                ChunkParagraphTaggingResult(
                    request.paragraphs[0].paragraph.paragraph_id,
                    (
                        ChunkTaggingLabel(
                            "harmony",
                            "create_new",
                            "Harmony",
                            (ContentRole.DEFINITION,),
                        ),
                    ),
                ),
            ),
        )


class FakeEmbeddingProvider:
    async def embed(self, chunks, *, source_version: str):
        return tuple(
            EmbeddingRecord(
                chunk_id=chunk_id,
                source_version=source_version,
                model_profile="embed-v1",
                vector=(0.1, 0.2),
            )
            for chunk_id, _ in chunks
        )


class RecordingVectorIndex:
    def __init__(self) -> None:
        self.records = ()

    async def upsert_chunks(self, records) -> None:
        self.records = tuple(records)

    async def delete_chunks(self, chunk_ids) -> None:
        raise AssertionError(f"unexpected delete: {chunk_ids}")


def _report() -> IngestionReport:
    return IngestionReport(
        document_ref="doc-1",
        source_version="source-v1",
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


@pytest.mark.anyio
async def test_run_scoped_chunk_ingestion_commits_replayable_vector_event_before_sync(
    tmp_path,
) -> None:
    database = tmp_path / "ingestion.sqlite3"
    vector_index = RecordingVectorIndex()
    workflow = IngestDocument(
        None,
        IndexDocument(vector_index, FakeEmbeddingProvider()),
        chunk_tagging=DocumentChunkTaggingService(
            ChunkTaggingTransactionService(
                ChunkTaggingService(FakeChunkTagger()),
                SqliteIngestionTransactionRepository(database),
            )
        ),
    )

    report = await workflow.execute(
        _command(),
        (_chunk(),),
        (_paragraph(),),
        resolution_profile="unused-for-chunk-tagging",
        ingestion_run_id="run-1",
    )

    assert report.indexed is True
    assert vector_index.records == ()

    outbox = SqliteVectorOutboxRepository(database)
    events = await outbox.list_pending(ingestion_run_id="run-1")
    assert len(events) == 1
    assert events[0].record_id == "chunk-1"
    assert events[0].index_version == "index-v1"

    relations = await SqliteTaggingRepository(database).list_relations("doc-1", "source-v1")
    assert relations[0].canonical_concept == "Harmony"
    assert relations[0].content_role is ContentRole.DEFINITION

    sync_report = await VectorSyncService(outbox, vector_index).sync_pending(
        ingestion_run_id="run-1"
    )

    assert sync_report == {"succeeded": 1, "failed": 0}
    assert vector_index.records[0].chunk_id == "chunk-1"
    assert vector_index.records[0].metadata["tags"] == ["Harmony"]


def test_run_scope_is_not_allowed_for_legacy_paragraph_tagging() -> None:
    class LegacyTagger:
        async def execute(self, paragraph, *, tagging_profile, resolution_profile):
            raise AssertionError("legacy tagger should not run")

    with pytest.raises(ValueError, match="chunk tagging workflow"):
        asyncio.run(
            IngestDocument(LegacyTagger(), IndexDocument(RecordingVectorIndex(), FakeEmbeddingProvider())).execute(
                _command(),
                (_chunk(),),
                (_paragraph(),),
                resolution_profile="resolve-v1",
                ingestion_run_id="run-1",
            )
        )


@pytest.mark.anyio
async def test_document_ingestion_service_forwards_run_scope_to_capable_workflow() -> None:
    class CapableWorkflow:
        def __init__(self) -> None:
            self.run_ids: list[str | None] = []

        async def execute(
            self,
            command,
            chunks,
            paragraphs,
            *,
            resolution_profile,
            ingestion_run_id=None,
        ):
            self.run_ids.append(ingestion_run_id)
            return _report()

    class Lifecycle:
        async def start_or_resume(self, **kwargs):
            return None

        async def mark_tagged_pending_vector_sync(self, ingestion_run_id):
            return None

        async def mark_ready(self, ingestion_run_id, *, pending_event_count=0):
            return None

        async def mark_failed(self, ingestion_run_id, *, error_code):
            return None

    class Sync:
        async def sync_pending(self, *, ingestion_run_id, limit):
            return {"succeeded": 0, "failed": 0}

        async def pending_count(self, *, ingestion_run_id):
            return 0

    workflow = CapableWorkflow()
    result = await DocumentIngestionService(
        workflow,
        vector_sync=Sync(),
        lifecycle=Lifecycle(),
    ).ingest_document(
        _command(),
        (),
        (),
        resolution_profile="resolve-v1",
        ingestion_run_id="run-1",
        source_hash="hash-1",
    )

    assert result.indexed is True
    assert workflow.run_ids == ["run-1"]
