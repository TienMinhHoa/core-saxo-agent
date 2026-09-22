from __future__ import annotations

import pytest

from saxophone.ingestion.concept_records import build_concept_vector_record
from saxophone.ingestion.models import EmbeddingRecord, IngestionCommand, IngestionSourceChunk
from saxophone.ingestion.transaction import SqliteIngestionTransactionRepository
from saxophone.ingestion.use_cases import (
    DocumentChunkTaggingService,
    IndexDocument,
    IngestDocument,
)
from saxophone.ingestion.vector_events import build_concept_vector_upsert_event
from saxophone.ingestion.vector_sync import VectorSyncService
from saxophone.tagging.chunk_models import (
    ChunkParagraphTaggingResult,
    ChunkTaggingLabel,
    ChunkTaggingRequest,
    ChunkTaggingResult,
)
from saxophone.tagging.chunk_service import ChunkTaggingService, ChunkTaggingTransactionService
from saxophone.tagging.concepts import ConceptCandidate
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
        self.chunk_records = []
        self.concept_records = []

    async def upsert_chunks(self, records) -> None:
        self.chunk_records.extend(records)

    async def delete_chunks(self, chunk_ids) -> None:
        return None

    async def upsert_concepts(self, records) -> None:
        self.concept_records.extend(records)

    async def delete_concepts(self, record_ids) -> None:
        return None


def _concept_event(*, ingestion_run_id: str = "run-66"):
    record = build_concept_vector_record(
        ConceptCandidate(canonical_label="Harmony", rank=1, semantic_score=0.9, usage_count=1),
        embedding=(0.3, 0.4),
        embedding_model="embed-v1",
        index_version="index-v1",
    )
    return build_concept_vector_upsert_event(
        record,
        catalog_ref="concept-catalog",
        catalog_version="catalog-v1",
        index_version="index-v1",
        ingestion_run_id=ingestion_run_id,
    )


def _workflow(database, vector_index: RecordingVectorIndex | None = None) -> IngestDocument:
    return IngestDocument(
        None,
        IndexDocument(vector_index or RecordingVectorIndex(), FakeEmbeddingProvider()),
        chunk_tagging=DocumentChunkTaggingService(
            ChunkTaggingTransactionService(
                ChunkTaggingService(FakeChunkTagger()),
                SqliteIngestionTransactionRepository(database),
            )
        ),
    )


@pytest.mark.anyio
async def test_run_scoped_ingestion_commits_concept_event_with_document_tagging(
    tmp_path,
) -> None:
    database = tmp_path / "ingestion.sqlite3"
    vector_index = RecordingVectorIndex()

    report = await _workflow(database, vector_index).execute(
        _command(),
        (_chunk(),),
        (_paragraph(),),
        resolution_profile="unused-for-chunk-tagging",
        ingestion_run_id="run-66",
        concept_outbox_events=(_concept_event(),),
    )

    assert report.indexed is True
    events = await SqliteVectorOutboxRepository(database).list_pending(ingestion_run_id="run-66")
    assert {event.collection for event in events} == {"document_chunks", "concept_catalog"}
    assert await SqliteTaggingRepository(database).list_relations("doc-1", "source-v1")

    sync_report = await VectorSyncService(
        SqliteVectorOutboxRepository(database),
        vector_index,
    ).sync_pending(ingestion_run_id="run-66")

    assert sync_report == {"succeeded": 2, "failed": 0}
    assert [record.canonical_label for record in vector_index.concept_records] == ["Harmony"]


@pytest.mark.anyio
async def test_concept_event_scope_is_rejected_before_relations_commit(tmp_path) -> None:
    database = tmp_path / "ingestion.sqlite3"
    wrong_scope = _concept_event(ingestion_run_id="run-66").__class__(
        event_id="wrong-scope",
        document_ref="doc-1",
        source_version="source-v1",
        collection="document_chunks",
        record_id="chunk-foreign",
        operation="upsert",
        payload_json="{}",
        ingestion_run_id="run-66",
        index_version="index-v1",
    )

    with pytest.raises(ValueError, match="concept outbox events"):
        await _workflow(database).execute(
            _command(),
            (_chunk(),),
            (_paragraph(),),
            resolution_profile="unused-for-chunk-tagging",
            ingestion_run_id="run-66",
            concept_outbox_events=(wrong_scope,),
        )

    assert await SqliteTaggingRepository(database).list_relations("doc-1", "source-v1") == ()
