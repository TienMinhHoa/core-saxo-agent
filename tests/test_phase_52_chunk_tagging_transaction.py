from __future__ import annotations

import pytest

from saxophone.tagging.chunk_models import (
    ChunkParagraphTaggingInput,
    ChunkParagraphTaggingResult,
    ChunkTaggingLabel,
    ChunkTaggingRequest,
    ChunkTaggingResult,
)
from saxophone.tagging.chunk_service import (
    ChunkTaggingService,
    ChunkTaggingTransactionService,
)
from saxophone.tagging.models import ContentRole, ParagraphBlock, ParagraphConceptRole
from saxophone.tagging.vector_outbox import VectorOutboxEvent


def _request() -> ChunkTaggingRequest:
    paragraphs = (
        ParagraphBlock("chunk-1:p1", "chunk-1", 0, "Harmony combines notes."),
        ParagraphBlock("chunk-1:p2", "chunk-1", 1, "Use harmony in this exercise."),
    )
    return ChunkTaggingRequest(
        "chunk-1", tuple(ChunkParagraphTaggingInput(item) for item in paragraphs)
    )


def _result() -> ChunkTaggingResult:
    return ChunkTaggingResult(
        chunk_id="chunk-1",
        chunk_new_concepts=("Harmony",),
        paragraphs=(
            ChunkParagraphTaggingResult(
                "chunk-1:p1",
                (
                    ChunkTaggingLabel(
                        "harmony",
                        "create_new",
                        "Harmony",
                        (ContentRole.DEFINITION,),
                    ),
                ),
            ),
            ChunkParagraphTaggingResult(
                "chunk-1:p2",
                (
                    ChunkTaggingLabel(
                        "harmony",
                        "reuse_chunk_new",
                        "Harmony",
                        (ContentRole.EXERCISE,),
                    ),
                ),
            ),
        ),
    )


class _Tagger:
    def __init__(self, result: ChunkTaggingResult) -> None:
        self.result = result
        self.calls: list[ChunkTaggingRequest] = []

    async def tag(self, request: ChunkTaggingRequest) -> ChunkTaggingResult:
        self.calls.append(request)
        return self.result


class _Committer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def commit_chunk(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def _event() -> VectorOutboxEvent:
    return VectorOutboxEvent(
        event_id="event-1",
        ingestion_run_id="run-1",
        document_ref="doc-1",
        source_version="v1",
        collection="document_chunks",
        record_id="chunk-1",
        operation="upsert",
        payload_json='{"record_id":"chunk-1"}',
        index_version="index-v1",
    )


@pytest.mark.anyio
async def test_transaction_service_commits_validated_relations_and_outbox_atomically() -> None:
    committer = _Committer()
    service = ChunkTaggingTransactionService(ChunkTaggingService(_Tagger(_result())), committer)

    run = await service.tag_and_commit(
        "doc-1",
        "v1",
        _request(),
        outbox_events=(_event(),),
    )

    assert run.relations == (
        ParagraphConceptRole("chunk-1:p1", "Harmony", ContentRole.DEFINITION),
        ParagraphConceptRole("chunk-1:p2", "Harmony", ContentRole.EXERCISE),
    )
    assert committer.calls == [
        {
            "document_ref": "doc-1",
            "source_version": "v1",
            "paragraph_ids": ("chunk-1:p1", "chunk-1:p2"),
            "relations": run.relations,
            "outbox_events": (_event(),),
        }
    ]


@pytest.mark.anyio
async def test_transaction_service_does_not_commit_invalid_tagging_output() -> None:
    committer = _Committer()
    invalid = ChunkTaggingResult("other-chunk", (), ())
    service = ChunkTaggingTransactionService(ChunkTaggingService(_Tagger(invalid)), committer)

    with pytest.raises(ValueError, match="chunk_id"):
        await service.tag_and_commit("doc-1", "v1", _request())

    assert committer.calls == []


def test_transaction_service_validates_commit_scope_before_provider_work() -> None:
    committer = _Committer()
    tagger = _Tagger(_result())
    service = ChunkTaggingTransactionService(ChunkTaggingService(tagger), committer)

    with pytest.raises(ValueError, match="document_ref"):
        import asyncio

        asyncio.run(service.tag_and_commit("../unsafe", "v1", _request()))

    assert committer.calls == []
    assert tagger.calls == []
