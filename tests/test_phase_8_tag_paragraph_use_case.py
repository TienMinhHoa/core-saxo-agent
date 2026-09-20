from __future__ import annotations

import pytest

from saxophone.tagging.models import (
    ExistingTagCandidate,
    ParagraphBlock,
    TagConflictResolution,
    TagGenerationResult,
)
from saxophone.tagging.use_cases import TagParagraph


class _Generator:
    async def generate(self, request):
        return TagGenerationResult(
            paragraph_id=request.paragraph.paragraph_id,
            tags=("Concept of harmony", "Harmonics"),
            tagging_profile=request.tagging_profile,
        )


class _Resolver:
    async def resolve(self, request):
        return TagConflictResolution(
            paragraph_id=request.paragraph_id,
            resolutions=(
                ("Concept of harmony", "reuse_existing", "Harmony definition"),
                ("Harmonics", "keep_new", "Harmonics"),
            ),
            resolution_profile=request.resolution_profile,
            generated_tags=request.generated_tags,
            existing_tags=tuple(candidate.tag for candidate in request.existing_tags),
        )


def _paragraph() -> ParagraphBlock:
    return ParagraphBlock(
        paragraph_id="chunk-1:p0000",
        chunk_id="chunk-1",
        ordinal=0,
        text="Harmony describes how chords relate to one another.",
    )


@pytest.mark.anyio
async def test_tag_paragraph_runs_generation_then_resolution_and_preserves_source() -> None:
    result = await TagParagraph(_Generator(), _Resolver()).execute(
        _paragraph(),
        tagging_profile="topic-tags-v1",
        resolution_profile="tag-conflicts-v1",
        existing_tags=(ExistingTagCandidate("Harmony definition"),),
    )

    assert result.paragraph_id == "chunk-1:p0000"
    assert result.text == _paragraph().text
    assert result.generated_tags == ("Concept of harmony", "Harmonics")
    assert result.tags == ("Harmony definition", "Harmonics")
    assert result.status == "completed"


@pytest.mark.anyio
async def test_tag_paragraph_rejects_resolution_for_another_paragraph() -> None:
    class _WrongResolver(_Resolver):
        async def resolve(self, request):
            return TagConflictResolution(
                paragraph_id="other:p0000",
                resolutions=(("Concept", "keep_new", "Concept"),),
                resolution_profile=request.resolution_profile,
                generated_tags=("Concept",),
            )

    with pytest.raises(ValueError, match="paragraph ID"):
        await TagParagraph(_Generator(), _WrongResolver()).execute(
            _paragraph(),
            tagging_profile="topic-tags-v1",
            resolution_profile="tag-conflicts-v1",
        )


@pytest.mark.anyio
async def test_tag_paragraph_does_not_silently_fallback_when_generation_fails() -> None:
    class _FailingGenerator:
        async def generate(self, request):
            raise RuntimeError("provider schema failure")

    with pytest.raises(RuntimeError, match="provider schema failure"):
        await TagParagraph(_FailingGenerator(), _Resolver()).execute(
            _paragraph(),
            tagging_profile="topic-tags-v1",
            resolution_profile="tag-conflicts-v1",
        )
