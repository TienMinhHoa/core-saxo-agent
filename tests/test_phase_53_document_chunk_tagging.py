from __future__ import annotations

import pytest

from saxophone.ingestion.models import EmbeddingRecord, IngestionCommand, IngestionSourceChunk
from saxophone.ingestion.use_cases import (
    DocumentChunkTaggingService,
    IndexDocument,
    IngestDocument,
    build_chunk_tagging_requests,
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


def _chunk(chunk_id: str, text: str) -> IngestionSourceChunk:
    return IngestionSourceChunk(
        chunk_id=chunk_id,
        document_ref="doc-1",
        source_version="source-v1",
        search_text=text,
        access_scope="tenant-a",
        metadata={"heading": chunk_id},
    )


def _paragraph(
    paragraph_id: str,
    chunk_id: str,
    ordinal: int,
    text: str,
    *,
    image_refs: tuple[str, ...] = (),
    image_captions: dict[str, str] | None = None,
) -> ParagraphBlock:
    return ParagraphBlock(
        paragraph_id=paragraph_id,
        chunk_id=chunk_id,
        ordinal=ordinal,
        text=text,
        image_refs=image_refs,
        image_captions=image_captions or {},
    )


class FakeChunkTagger:
    def __init__(self) -> None:
        self.calls: list[ChunkTaggingRequest] = []

    async def tag(self, request: ChunkTaggingRequest) -> ChunkTaggingResult:
        self.calls.append(request)
        labels = []
        for item in request.paragraphs:
            candidate = item.existing_candidates[0] if item.existing_candidates else "New concept"
            action = "reuse_existing" if item.existing_candidates else "create_new"
            labels.append(
                ChunkParagraphTaggingResult(
                    item.paragraph.paragraph_id,
                    (
                        ChunkTaggingLabel(
                            candidate,
                            action,
                            candidate,
                            (ContentRole.DEFINITION,),
                        ),
                    ),
                )
            )
        concepts = tuple(
            dict.fromkeys(
                label.resolved_concept
                for paragraph in labels
                for label in paragraph.labels
                if label.action != "reuse_existing"
            )
        )
        return ChunkTaggingResult(request.chunk_id, concepts, tuple(labels))


class RecordingCommitter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def commit_chunk(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


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
        self.records = tuple(records)


@pytest.mark.anyio
async def test_document_chunk_tagging_builds_context_and_commits_once_per_chunk() -> None:
    chunk_one = _chunk("chunk-1", "First.\n\nSecond.")
    chunk_two = _chunk("chunk-2", "Third.")
    paragraphs = (
        _paragraph("chunk-1:p1", "chunk-1", 0, "First."),
        _paragraph(
            "chunk-1:p2",
            "chunk-1",
            1,
            "Second.",
            image_refs=("figure-1",),
            image_captions={"figure-1": "A cadence diagram."},
        ),
        _paragraph("chunk-2:p1", "chunk-2", 0, "Third."),
    )
    tagger = FakeChunkTagger()
    committer = RecordingCommitter()
    event = VectorOutboxEvent(
        event_id="chunk-event-1",
        document_ref="doc-1",
        source_version="source-v1",
        collection="document_chunks",
        record_id="chunk-1",
        operation="upsert",
        payload_json='{"record":{}}',
    )
    service = DocumentChunkTaggingService(
        ChunkTaggingTransactionService(ChunkTaggingService(tagger), committer)
    )

    runs = await service.execute(
        _command(),
        (chunk_one, chunk_two),
        paragraphs,
        existing_candidates={"chunk-1:p1": ("Harmony",)},
        outbox_events={"chunk-1": (event,)},
    )

    assert len(runs) == 2
    assert len(tagger.calls) == 2
    first_request = tagger.calls[0]
    assert [item.paragraph.paragraph_id for item in first_request.paragraphs] == [
        "chunk-1:p1",
        "chunk-1:p2",
    ]
    assert first_request.paragraphs[0].existing_candidates == ("Harmony",)
    assert first_request.paragraphs[0].previous_context == ""
    assert first_request.paragraphs[0].next_context == "Second."
    assert first_request.paragraphs[1].previous_context == "First."
    assert first_request.paragraphs[1].image_context == ("A cadence diagram.",)
    assert [call["paragraph_ids"] for call in committer.calls] == [
        ("chunk-1:p1", "chunk-1:p2"),
        ("chunk-2:p1",),
    ]
    assert committer.calls[0]["outbox_events"] == (event,)
    assert committer.calls[1]["outbox_events"] == ()


def test_chunk_tagging_request_builder_rejects_chunks_without_paragraphs() -> None:
    with pytest.raises(ValueError, match="every chunk must have at least one paragraph"):
        build_chunk_tagging_requests(
            (_chunk("chunk-1", "Source."),),
            (),
        )


@pytest.mark.anyio
async def test_ingest_document_can_use_chunk_tagging_transaction_for_index_projection() -> None:
    chunk = _chunk("chunk-1", "Source.")
    paragraph = _paragraph("chunk-1:p1", "chunk-1", 0, "Source.")
    tagger = FakeChunkTagger()
    committer = RecordingCommitter()
    index = FakeVectorIndex()
    workflow = IngestDocument(
        None,
        IndexDocument(index, FakeEmbeddingProvider()),
        chunk_tagging=DocumentChunkTaggingService(
            ChunkTaggingTransactionService(ChunkTaggingService(tagger), committer)
        ),
    )

    report = await workflow.execute(
        _command(),
        (chunk,),
        (paragraph,),
        resolution_profile="unused-for-chunk-tagging",
    )

    assert report.indexed is True
    assert len(tagger.calls) == 1
    assert index.records[0].metadata["tags"] == ("New concept",)
    assert committer.calls[0]["relations"]
