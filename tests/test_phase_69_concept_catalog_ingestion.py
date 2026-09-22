from __future__ import annotations

import pytest

from saxophone.ingestion.concept_embedding import (
    ConceptCatalogVectorPreparationService,
)
from saxophone.ingestion.concept_repository import SqliteConceptCatalogRepository
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
from saxophone.tagging.concepts import ConceptCandidateExample
from saxophone.tagging.models import ContentRole, ParagraphBlock
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository
from saxophone.ingestion.concept_catalog import ConceptCatalogEntry


def _command(*, source_version: str = "source-v1") -> IngestionCommand:
    return IngestionCommand(
        document_ref="doc-1",
        source_version=source_version,
        chunking_profile="header-v1",
        tagging_profile="topic-v1",
        embedding_profile="text-embedding-3-small",
        index_profile="topic-index-v1",
        access_scope="tenant-a",
    )


def _chunk(*, source_version: str = "source-v1") -> IngestionSourceChunk:
    return IngestionSourceChunk(
        chunk_id="chunk-1",
        document_ref="doc-1",
        source_version=source_version,
        search_text="Harmony combines notes.",
        access_scope="tenant-a",
        metadata={"heading": "Harmony"},
    )


def _paragraph(*, source_version: str = "source-v1") -> ParagraphBlock:
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


def _workflow(
    database,
    concept_repository: SqliteConceptCatalogRepository,
    concept_provider: _ConceptEmbeddingProvider,
) -> IngestDocument:
    return IngestDocument(
        None,
        IndexDocument(_VectorIndex(), _ChunkEmbeddingProvider()),
        chunk_tagging=DocumentChunkTaggingService(
            ChunkTaggingTransactionService(
                ChunkTaggingService(_ChunkTagger()),
                SqliteIngestionTransactionRepository(database),
            )
        ),
        concept_catalog_repository=concept_repository,
        concept_vector_preparation=ConceptCatalogVectorPreparationService(
            concept_provider
        ),
    )


@pytest.mark.anyio
async def test_ingestion_embeds_the_reconciled_global_catalog(tmp_path) -> None:
    database = tmp_path / "ingestion.sqlite3"
    repository = SqliteConceptCatalogRepository(database)
    await repository.replace_document_entries(
        "doc-0",
        "source-v1",
        (
            ConceptCatalogEntry(
                canonical_label="Theory",
                normalized_label="",
                usage_count=1,
                examples=(),
            ),
        ),
    )
    provider = _ConceptEmbeddingProvider()

    report = await _workflow(database, repository, provider).execute(
        _command(),
        (_chunk(),),
        (_paragraph(),),
        resolution_profile="unused",
        ingestion_run_id="run-69",
    )

    assert report.indexed is True
    assert provider.calls == [
        ("Harmony\nHarmony: Harmony combines notes.", "Theory")
    ]
    events = await repository.list_entries()
    assert tuple(entry.normalized_label for entry in events) == ("harmony", "theory")
    pending = await SqliteVectorOutboxRepository(database).list_pending(
        ingestion_run_id="run-69"
    )
    assert sum(event.collection == "concept_catalog" for event in pending) == 2


@pytest.mark.anyio
async def test_reingestion_replaces_prior_catalog_observation_before_embedding(
    tmp_path,
) -> None:
    database = tmp_path / "ingestion.sqlite3"
    repository = SqliteConceptCatalogRepository(database)
    await repository.replace_document_entries(
        "doc-1",
        "source-v1",
        (
            ConceptCatalogEntry(
                canonical_label="Harmony",
                normalized_label="",
                usage_count=2,
                examples=(ConceptCandidateExample("Old", "Old excerpt."),),
            ),
            ConceptCatalogEntry(
                canonical_label="Legacy",
                normalized_label="",
                usage_count=1,
                examples=(),
            ),
        ),
    )
    provider = _ConceptEmbeddingProvider()

    await _workflow(database, repository, provider).execute(
        _command(source_version="source-v2"),
        (_chunk(source_version="source-v2"),),
        (_paragraph(source_version="source-v2"),),
        resolution_profile="unused",
        ingestion_run_id="run-69-reingest",
        previous_source_versions=("source-v1",),
    )

    assert provider.calls == [("Harmony\nHarmony: Harmony combines notes.",)]
    entries = await repository.list_entries()
    assert entries == (
        ConceptCatalogEntry(
            canonical_label="Harmony",
            normalized_label="harmony",
            usage_count=1,
            examples=(
                ConceptCandidateExample("Harmony", "Harmony combines notes."),
            ),
        ),
    )
