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
    assert result.chunk_id == "chunk-1"
    assert result.ordinal == 0
    assert result.heading_path == ()
    assert result.image_refs == ()


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
async def test_tag_paragraph_rejects_generation_profile_drift() -> None:
    class _DriftedGenerator(_Generator):
        async def generate(self, request):
            result = await super().generate(request)
            return TagGenerationResult(
                paragraph_id=result.paragraph_id,
                tags=result.tags,
                tagging_profile="older-profile",
            )

    with pytest.raises(ValueError, match="tagging profile"):
        await TagParagraph(_DriftedGenerator(), _Resolver()).execute(
            _paragraph(),
            tagging_profile="topic-tags-v1",
            resolution_profile="tag-conflicts-v1",
        )


@pytest.mark.anyio
async def test_tag_paragraph_rejects_resolution_profile_drift() -> None:
    class _DriftedResolver(_Resolver):
        async def resolve(self, request):
            result = await super().resolve(request)
            return TagConflictResolution(
                paragraph_id=result.paragraph_id,
                resolutions=result.resolutions,
                resolution_profile="older-profile",
                generated_tags=result.generated_tags,
                existing_tags=result.existing_tags,
            )

    with pytest.raises(ValueError, match="resolution profile"):
        await TagParagraph(_Generator(), _DriftedResolver()).execute(
            _paragraph(),
            tagging_profile="topic-tags-v1",
            resolution_profile="tag-conflicts-v1",
            existing_tags=(ExistingTagCandidate("Harmony definition"),),
        )


@pytest.mark.anyio
async def test_tag_paragraph_rejects_missing_resolution_generated_tags() -> None:
    class _MissingGeneratedTagsResolver:
        async def resolve(self, request):
            return type(
                "ResolutionWithoutGenerationContract",
                (),
                {
                    "paragraph_id": request.paragraph_id,
                    "resolution_profile": request.resolution_profile,
                    "generated_tags": (),
                    "resolutions": tuple(
                        type("Resolution", (), {"resolved_tag": tag})
                        for tag in request.generated_tags
                    ),
                },
            )()

    with pytest.raises(ValueError, match="generated tags"):
        await TagParagraph(_Generator(), _MissingGeneratedTagsResolver()).execute(
            _paragraph(),
            tagging_profile="topic-tags-v1",
            resolution_profile="tag-conflicts-v1",
        )


@pytest.mark.anyio
async def test_tag_paragraph_rejects_resolution_order_drift() -> None:
    class _ReorderedResolver(_Resolver):
        async def resolve(self, request):
            result = await super().resolve(request)
            return TagConflictResolution(
                paragraph_id=result.paragraph_id,
                resolutions=tuple(reversed(result.resolutions)),
                resolution_profile=result.resolution_profile,
                generated_tags=result.generated_tags,
                existing_tags=("Harmony definition",),
            )

    with pytest.raises(ValueError, match="resolution order"):
        await TagParagraph(_Generator(), _ReorderedResolver()).execute(
            _paragraph(),
            tagging_profile="topic-tags-v1",
            resolution_profile="tag-conflicts-v1",
            existing_tags=(ExistingTagCandidate("Harmony definition"),),
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


@pytest.mark.anyio
async def test_tag_paragraph_preserves_source_provenance_projection() -> None:
    paragraph = ParagraphBlock(
        paragraph_id="chunk-1:p0000",
        chunk_id="chunk-1",
        ordinal=3,
        text="Harmony source",
        heading_path=("Music", "Harmony"),
        image_refs=("images/harmony.png",),
        image_captions={"images/harmony.png": "Harmony diagram"},
    )

    result = await TagParagraph(_Generator(), _Resolver()).execute(
        paragraph,
        tagging_profile="topic-tags-v1",
        resolution_profile="tag-conflicts-v1",
        existing_tags=(ExistingTagCandidate("Harmony definition"),),
    )

    assert result.chunk_id == paragraph.chunk_id
    assert result.ordinal == paragraph.ordinal
    assert result.heading_path == paragraph.heading_path
    assert result.image_refs == paragraph.image_refs
    assert dict(result.image_captions) == dict(paragraph.image_captions)
