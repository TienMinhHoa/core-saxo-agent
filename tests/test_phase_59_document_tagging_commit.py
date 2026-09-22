from __future__ import annotations

import pytest

from saxophone.ingestion.models import EmbeddingRecord, IngestionCommand, IngestionSourceChunk
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
from saxophone.tagging.chunk_service import ChunkTaggingService, ChunkTaggingTransactionService
from saxophone.tagging.models import ContentRole, ParagraphBlock
from saxophone.tagging.vector_outbox import VectorOutboxEvent


def _command(*, source_version: str = "source-v2") -> IngestionCommand:
    return IngestionCommand(
        document_ref="doc-1",
        source_version=source_version,
        chunking_profile="chunk-v1",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
    )


def _chunk(chunk_id: str) -> IngestionSourceChunk:
    return IngestionSourceChunk(
        chunk_id=chunk_id,
        document_ref="doc-1",
        source_version="source-v2",
        search_text=f"Source for {chunk_id}.",
        access_scope="tenant-a",
        metadata={"heading": chunk_id},
    )


def _paragraph(paragraph_id: str, chunk_id: str, ordinal: int) -> ParagraphBlock:
    return ParagraphBlock(
        paragraph_id=paragraph_id,
        chunk_id=chunk_id,
        ordinal=ordinal,
        text=f"Text for {paragraph_id}.",
    )


class FakeChunkTagger:
    async def tag(self, request: ChunkTaggingRequest) -> ChunkTaggingResult:
        paragraphs = tuple(
            ChunkParagraphTaggingResult(
                item.paragraph.paragraph_id,
                (
                    ChunkTaggingLabel(
                        generated_concept=f"generated-{item.paragraph.paragraph_id}",
                        action="create_new",
                        resolved_concept=f"Concept {item.paragraph.paragraph_id}",
                        roles=(ContentRole.DEFINITION,),
                    ),
                ),
            )
            for item in request.paragraphs
        )
        new_concepts = tuple(
            label.resolved_concept
            for paragraph in paragraphs
            for label in paragraph.labels
        )
        return ChunkTaggingResult(request.chunk_id, new_concepts, paragraphs)


class RecordingDocumentCommitter:
    def __init__(self) -> None:
        self.chunk_calls: list[dict[str, object]] = []
        self.document_calls: list[dict[str, object]] = []

    async def commit_chunk(self, **kwargs: object) -> None:
        self.chunk_calls.append(kwargs)

    async def commit_document(self, **kwargs: object) -> None:
        self.document_calls.append(kwargs)


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


class FakeVectorIndex:
    async def upsert_chunks(self, records) -> None:
        raise AssertionError("run-scoped ingestion must defer vector publication")


def _service(committer: RecordingDocumentCommitter) -> DocumentChunkTaggingService:
    return DocumentChunkTaggingService(
        ChunkTaggingTransactionService(
            ChunkTaggingService(FakeChunkTagger()),
            committer,
        )
    )


@pytest.mark.anyio
async def test_document_commit_aggregates_prepared_chunk_relations_and_events() -> None:
    committer = RecordingDocumentCommitter()
    service = _service(committer)
    chunks = (_chunk("chunk-1"), _chunk("chunk-2"))
    paragraphs = (
        _paragraph("chunk-1:p1", "chunk-1", 0),
        _paragraph("chunk-2:p1", "chunk-2", 0),
    )
    prepared = await service.prepare(_command(), chunks, paragraphs)
    events = (
        VectorOutboxEvent(
            event_id="delete-old",
            ingestion_run_id="run-59",
            document_ref="doc-1",
            source_version="source-v1",
            collection="document_chunks",
            record_id="chunk-old",
            operation="delete",
            payload_json="{}",
            index_version="index-v1",
        ),
        VectorOutboxEvent(
            event_id="upsert-new",
            ingestion_run_id="run-59",
            document_ref="doc-1",
            source_version="source-v2",
            collection="document_chunks",
            record_id="chunk-1",
            operation="upsert",
            payload_json='{"record":{}}',
            index_version="index-v1",
        ),
    )

    await service.commit_document(
        _command(),
        prepared,
        outbox_events=events,
        previous_source_versions=("source-v1",),
    )

    assert committer.chunk_calls == []
    assert len(committer.document_calls) == 1
    call = committer.document_calls[0]
    assert call["document_ref"] == "doc-1"
    assert call["source_version"] == "source-v2"
    assert call["paragraph_ids"] == ("chunk-1:p1", "chunk-2:p1")
    assert [relation.paragraph_id for relation in call["relations"]] == [
        "chunk-1:p1",
        "chunk-2:p1",
    ]
    assert call["outbox_events"] == events
    assert call["previous_source_versions"] == ("source-v1",)


@pytest.mark.anyio
async def test_run_scoped_ingestion_uses_one_document_commit() -> None:
    committer = RecordingDocumentCommitter()
    workflow = IngestDocument(
        None,
        IndexDocument(FakeVectorIndex(), FakeEmbeddingProvider()),
        chunk_tagging=_service(committer),
    )

    report = await workflow.execute(
        _command(),
        (_chunk("chunk-1"), _chunk("chunk-2")),
        (
            _paragraph("chunk-1:p1", "chunk-1", 0),
            _paragraph("chunk-2:p1", "chunk-2", 0),
        ),
        resolution_profile="unused-for-chunk-tagging",
        ingestion_run_id="run-59",
    )

    assert report.indexed is True
    assert committer.chunk_calls == []
    assert len(committer.document_calls) == 1
    assert len(committer.document_calls[0]["outbox_events"]) == 2


@pytest.mark.anyio
async def test_document_commit_rejects_new_version_as_previous_scope() -> None:
    committer = RecordingDocumentCommitter()
    service = _service(committer)
    prepared = await service.prepare(
        _command(),
        (_chunk("chunk-1"),),
        (_paragraph("chunk-1:p1", "chunk-1", 0),),
    )

    with pytest.raises(ValueError, match="previous_source_versions"):
        await service.commit_document(
            _command(),
            prepared,
            previous_source_versions=("source-v2",),
        )

    assert committer.document_calls == []


@pytest.mark.anyio
async def test_previous_versions_require_run_scoped_ingestion() -> None:
    committer = RecordingDocumentCommitter()
    workflow = IngestDocument(
        None,
        IndexDocument(FakeVectorIndex(), FakeEmbeddingProvider()),
        chunk_tagging=_service(committer),
    )

    with pytest.raises(ValueError, match="ingestion_run_id"):
        await workflow.execute(
            _command(),
            (_chunk("chunk-1"),),
            (_paragraph("chunk-1:p1", "chunk-1", 0),),
            resolution_profile="unused-for-chunk-tagging",
            previous_source_versions=("source-v1",),
        )
