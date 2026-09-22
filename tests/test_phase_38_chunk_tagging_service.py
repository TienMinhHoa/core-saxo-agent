from __future__ import annotations

import pytest

from saxophone.tagging.chunk_models import (
    ChunkParagraphTaggingInput,
    ChunkParagraphTaggingResult,
    ChunkTaggingLabel,
    ChunkTaggingRequest,
    ChunkTaggingResult,
)
from saxophone.tagging.chunk_service import ChunkTaggingService
from saxophone.tagging.models import ContentRole, ParagraphBlock, ParagraphConceptRole


def _request() -> ChunkTaggingRequest:
    paragraphs = (
        ParagraphBlock("chunk-1:p1", "chunk-1", 0, "Harmony combines notes."),
        ParagraphBlock("chunk-1:p2", "chunk-1", 1, "Use harmony in this exercise."),
    )
    return ChunkTaggingRequest(
        "chunk-1", tuple(ChunkParagraphTaggingInput(item) for item in paragraphs)
    )


class _Tagger:
    def __init__(self, result: ChunkTaggingResult) -> None:
        self.result = result
        self.requests: list[ChunkTaggingRequest] = []

    async def tag(self, request: ChunkTaggingRequest) -> ChunkTaggingResult:
        self.requests.append(request)
        return self.result


@pytest.mark.anyio
async def test_chunk_tagging_service_makes_one_call_and_projects_relations() -> None:
    request = _request()
    result = ChunkTaggingResult(
        chunk_id="chunk-1",
        chunk_new_concepts=("Harmony",),
        paragraphs=(
            ChunkParagraphTaggingResult(
                "chunk-1:p1",
                (ChunkTaggingLabel("harmony", "create_new", "Harmony", (ContentRole.DEFINITION,)),),
            ),
            ChunkParagraphTaggingResult(
                "chunk-1:p2",
                (ChunkTaggingLabel("harmony", "reuse_chunk_new", "Harmony", (ContentRole.EXERCISE, ContentRole.EXAMPLE)),),
            ),
        ),
    )
    tagger = _Tagger(result)

    run = await ChunkTaggingService(tagger).tag_chunk(request)

    assert tagger.requests == [request]
    assert run.result is result
    assert run.relations == (
        ParagraphConceptRole("chunk-1:p1", "Harmony", ContentRole.DEFINITION),
        ParagraphConceptRole("chunk-1:p2", "Harmony", ContentRole.EXERCISE),
        ParagraphConceptRole("chunk-1:p2", "Harmony", ContentRole.EXAMPLE),
    )


@pytest.mark.anyio
async def test_chunk_tagging_service_rejects_foreign_result_before_projection() -> None:
    request = _request()
    result = ChunkTaggingResult("other-chunk", (), ())

    with pytest.raises(ValueError, match="chunk_id"):
        await ChunkTaggingService(_Tagger(result)).tag_chunk(request)


@pytest.mark.anyio
async def test_chunk_tagging_service_rejects_invalid_collaborator_output() -> None:
    class _InvalidTagger:
        async def tag(self, request: ChunkTaggingRequest) -> object:
            return object()

    with pytest.raises(TypeError, match="ChunkTaggingResult"):
        await ChunkTaggingService(_InvalidTagger()).tag_chunk(_request())
