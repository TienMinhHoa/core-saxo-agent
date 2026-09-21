from __future__ import annotations

import pytest

from saxophone.tagging.models import (
    ContentRole,
    ParagraphBlock,
    ParagraphConceptRole,
    TagGenerationRequest,
    TagGenerationResult,
)
from saxophone.tagging.ports import TagGenerator


def _paragraph() -> ParagraphBlock:
    return ParagraphBlock(
        paragraph_id="chunk-1:p-0",
        chunk_id="chunk-1",
        ordinal=0,
        text="Harmony describes how chords relate to one another.",
    )


def test_tag_generation_contract_keeps_source_paragraph_and_plain_english_tags() -> None:
    request = TagGenerationRequest(paragraph=_paragraph(), tagging_profile="topic-tags-v1")
    result = TagGenerationResult(
        paragraph_id=request.paragraph.paragraph_id,
        tags=("Harmony", "Chord progression"),
        tagging_profile=request.tagging_profile,
    )

    assert result.paragraph_id == request.paragraph.paragraph_id
    assert result.tags == ("Harmony", "Chord progression")
    assert request.paragraph.text.startswith("Harmony")


@pytest.mark.parametrize("field", ["paragraph_id", "chunk_id", "text"])
def test_paragraph_block_rejects_blank_identity_or_source_text(field: str) -> None:
    values = {"paragraph_id": "p-1", "chunk_id": "chunk-1", "ordinal": 0, "text": "source"}
    values[field] = " "

    with pytest.raises(ValueError, match=field):
        ParagraphBlock(**values)


def test_tag_result_rejects_duplicate_or_non_string_tags() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        TagGenerationResult("p-1", ("Harmony", "Harmony"), "topic-tags-v1")
    with pytest.raises(ValueError, match="non-blank"):
        TagGenerationResult("p-1", (" ",), "topic-tags-v1")


def test_tag_generator_is_an_async_provider_port() -> None:
    assert hasattr(TagGenerator, "generate")


def test_paragraph_concept_role_keeps_role_attached_to_its_concept() -> None:
    relation = ParagraphConceptRole(
        paragraph_id="chunk-1:p-0",
        canonical_concept="Major triad",
        content_role=ContentRole.DEFINITION,
    )

    assert relation.canonical_concept == "Major triad"
    assert relation.content_role is ContentRole.DEFINITION


def test_content_role_rejects_unknown_values_and_relation_rejects_blank_concepts() -> None:
    with pytest.raises(ValueError, match="content_role"):
        ParagraphConceptRole("p-1", "Harmony", "Unknown")
    with pytest.raises(ValueError, match="canonical_concept"):
        ParagraphConceptRole("p-1", " ", ContentRole.EXPLANATION)
