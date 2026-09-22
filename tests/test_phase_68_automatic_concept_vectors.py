from __future__ import annotations

import pytest

from saxophone.ingestion.concept_embedding import (
    ConceptCatalogVectorPreparationService,
)
from saxophone.ingestion.models import (
    EmbeddingRecord,
    IngestionCommand,
    IngestionSourceChunk,
)
from saxophone.ingestion.transaction import SqliteIngestionTransactionRepository
from saxophone.ingestion.use_cases import (
    DocumentChunkTaggingService,
    IndexDocument,
    IngestDocument,
)
from saxophone.tagging.chunk_models import (
    ChunkParagraphTaggingResult,
    ChunkTaggingLabel,
    ChunkTaggingRequest,
    ChunkTaggingResult,
)
from saxophone.tagging.chunk_service import (
    ChunkTaggingService,
    ChunkTaggingTransactionService,
)
from saxophone.tagging.models import ContentRole, ParagraphBlock
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository


def _command() -> IngestionCommand:
    return IngestionCommand(
        document_ref="doc-1",
        source_version="source-v1",
        chunking_profile="header-v1",
        tagging_profile="topic-v1",
        embedding_profile="text-embedding-3-small",
        index_profile="topic-index-v1",
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


class _ChunkTagger:
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


class _ChunkEmbeddingProvider:
    async def embed(self, chunks, *, source_version: str):
        return tuple(
            EmbeddingRecord(
                chunk_id=chunk_id,
                source_version=source_version,
                model_profile="text-embedding-3-small",
                vector=(0.1, 0.2),
            )
            for chunk_id, _ in chunks
        )


class _ConceptEmbeddingProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def embed_texts(self, texts):
        normalized = tuple(texts)
        self.calls.append(normalized)
        return tuple((0.3, 0.4) for _ in normalized)


class _VectorIndex:
    async def upsert_chunks(self, records) -> None:
        return None

    async def delete_chunks(self, chunk_ids) -> None:
        return None


@pytest.mark.anyio
async def test_run_scoped_ingestion_builds_concept_events_without_caller_payload(
    tmp_path,
) -> None:
    database = tmp_path / "ingestion.sqlite3"
    concept_provider = _ConceptEmbeddingProvider()
    workflow = IngestDocument(
        None,
        IndexDocument(_VectorIndex(), _ChunkEmbeddingProvider()),
        chunk_tagging=DocumentChunkTaggingService(
            ChunkTaggingTransactionService(
                ChunkTaggingService(_ChunkTagger()),
                SqliteIngestionTransactionRepository(database),
            )
        ),
        concept_vector_preparation=ConceptCatalogVectorPreparationService(
            concept_provider
        ),
    )

    report = await workflow.execute(
        _command(),
        (_chunk(),),
        (_paragraph(),),
        resolution_profile="unused",
        ingestion_run_id="run-68",
    )

    assert report.indexed is True
    assert concept_provider.calls == [("Harmony\nHarmony: Harmony combines notes.",)]
    events = await SqliteVectorOutboxRepository(database).list_pending(
        ingestion_run_id="run-68"
    )
    assert {event.collection for event in events} == {
        "document_chunks",
        "concept_catalog",
    }
    concept_event = next(
        event for event in events if event.collection == "concept_catalog"
    )
    assert concept_event.document_ref == "concept-catalog"
    assert concept_event.index_version == "topic-index-v1"


@pytest.mark.anyio
async def test_automatic_concept_vectors_require_run_scoped_atomic_ingestion(
    tmp_path,
) -> None:
    workflow = IngestDocument(
        None,
        IndexDocument(_VectorIndex(), _ChunkEmbeddingProvider()),
        chunk_tagging=DocumentChunkTaggingService(
            ChunkTaggingTransactionService(
                ChunkTaggingService(_ChunkTagger()),
                SqliteIngestionTransactionRepository(tmp_path / "ingestion.sqlite3"),
            )
        ),
        concept_vector_preparation=ConceptCatalogVectorPreparationService(
            _ConceptEmbeddingProvider()
        ),
    )

    with pytest.raises(ValueError, match="ingestion_run_id"):
        await workflow.execute(
            _command(),
            (_chunk(),),
            (_paragraph(),),
            resolution_profile="unused",
        )
