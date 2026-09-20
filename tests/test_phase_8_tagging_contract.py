from __future__ import annotations

import pytest

from saxophone.tagging.models import ParagraphBlock, TagGenerationRequest, TagGenerationResult
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
