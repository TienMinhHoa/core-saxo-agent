from __future__ import annotations

import pytest

from saxophone.ingestion.models import (
    EmbeddingRecord,
    IngestionCommand,
    IngestionSourceChunk,
)
from saxophone.ingestion.use_cases import (
    DocumentChunkTaggingService,
    IndexDocument,
    IngestDocument,
)
from saxophone.ingestion.vector_state import VectorIndexState, VectorStateReconciliation
from saxophone.tagging.chunk_models import (
    ChunkParagraphTaggingResult,
    ChunkTaggingLabel,
    ChunkTaggingRequest,
    ChunkTaggingResult,
)
from saxophone.tagging.chunk_service import ChunkTaggingService, ChunkTaggingTransactionService
from saxophone.tagging.models import ContentRole, ParagraphBlock


def _command() -> IngestionCommand:
    return IngestionCommand(
        document_ref="doc-1",
        source_version="source-v2",
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


def _paragraph(paragraph_id: str, chunk_id: str, ordinal: int = 0) -> ParagraphBlock:
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
        return ChunkTaggingResult(
            request.chunk_id,
            tuple(
                label.resolved_concept
                for paragraph in paragraphs
                for label in paragraph.labels
            ),
            paragraphs,
        )


class RecordingCommitter:
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


class DeferredVectorIndex:
    async def upsert_chunks(self, records) -> None:
        raise AssertionError("run-scoped ingestion must defer vector publication")

    async def delete_chunks(self, chunk_ids) -> None:
        raise AssertionError("run-scoped ingestion must defer vector publication")


class PublishingVectorIndex:
    async def upsert_chunks(self, records) -> None:
        return None

    async def delete_chunks(self, chunk_ids) -> None:
        return None


class RecordingVectorState:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def plan_reconciliation(self, **kwargs: object) -> VectorStateReconciliation:
        self.calls.append(kwargs)
        desired = {state.entity_key: state for state in kwargs["desired"]}
        return VectorStateReconciliation(
            unchanged=(desired["chunk-kept"],),
            changed=(),
            new=(desired["chunk-new"],),
            stale=(
                VectorIndexState(
                    entity_type="chunk",
                    entity_key="chunk-old",
                    collection_name="document_chunks",
                    chroma_record_id="chunk-old",
                    embedding_input_hash="a" * 64,
                    embedding_model="embed-v1",
                    embedding_dimensions=2,
                    index_version="index-v1",
                    document_ref="doc-1",
                    source_version="source-v1",
                ),
            ),
        )


def _workflow(
    committer: RecordingCommitter,
    vector_state: RecordingVectorState,
    *,
    vector_index: object | None = None,
) -> IngestDocument:
    tagging = DocumentChunkTaggingService(
        ChunkTaggingTransactionService(
            ChunkTaggingService(FakeChunkTagger()),
            committer,
        )
    )
    return IngestDocument(
        None,
        IndexDocument(vector_index or DeferredVectorIndex(), FakeEmbeddingProvider()),
        chunk_tagging=tagging,
        vector_state=vector_state,
    )


@pytest.mark.anyio
async def test_run_scoped_ingestion_reconciles_chunk_vectors_before_atomic_commit() -> None:
    committer = RecordingCommitter()
    vector_state = RecordingVectorState()
    workflow = _workflow(committer, vector_state)

    report = await workflow.execute(
        _command(),
        (_chunk("chunk-kept"), _chunk("chunk-new")),
        (
            _paragraph("chunk-kept:p1", "chunk-kept"),
            _paragraph("chunk-new:p1", "chunk-new"),
        ),
        resolution_profile="unused-for-chunk-tagging",
        ingestion_run_id="run-62",
        previous_source_versions=("source-v1",),
    )

    assert report.indexed is True
    assert len(vector_state.calls) == 1
    plan = vector_state.calls[0]
    assert plan["entity_type"] == "chunk"
    assert plan["collection_name"] == "document_chunks"
    assert plan["index_version"] == "index-v1"
    assert plan["document_ref"] == "doc-1"
    assert [state.entity_key for state in plan["desired"]] == [
        "chunk-kept",
        "chunk-new",
    ]

    events = committer.document_calls[0]["outbox_events"]
    assert [(event.operation, event.record_id, event.source_version) for event in events] == [
        ("upsert", "chunk-new", "source-v2"),
        ("delete", "chunk-old", "source-v1"),
    ]


@pytest.mark.anyio
async def test_vector_state_planning_requires_a_run_scope() -> None:
    committer = RecordingCommitter()
    vector_state = RecordingVectorState()
    workflow = _workflow(
        committer,
        vector_state,
        vector_index=PublishingVectorIndex(),
    )

    report = await workflow.execute(
        _command(),
        (_chunk("chunk-1"),),
        (_paragraph("chunk-1:p1", "chunk-1"),),
        resolution_profile="unused-for-chunk-tagging",
    )

    assert report.indexed is True
    assert vector_state.calls == []
    assert committer.document_calls == []
    assert len(committer.chunk_calls) == 1
