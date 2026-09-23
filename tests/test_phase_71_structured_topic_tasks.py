from __future__ import annotations

import json

import pytest

from saxophone.retrieval.role_selection import (
    ConceptRoleCandidate,
    ConceptRoleSelectionRequest,
    StructuredConceptRoleSelector,
)
from saxophone.tagging.chunk_models import (
    ChunkParagraphTaggingInput,
    ChunkTaggingRequest,
)
from saxophone.tagging.models import ContentRole, ParagraphBlock
from saxophone.tagging.structured_chunk import StructuredChunkTagger
from saxophone.tagging.structured_provider import StructuredOutputMode


class _StructuredProvider:
    structured_output_mode = StructuredOutputMode.JSON_OBJECT

    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs["response_model"].model_validate(self.responses[kwargs["task_type"]])


def _tagging_request() -> ChunkTaggingRequest:
    paragraph = ParagraphBlock(
        "paragraph-1",
        "chunk-01",
        0,
        "A major triad has a root, third, and fifth.",
        heading_path=("Chords", "Triads"),
    )
    return ChunkTaggingRequest(
        "chunk-01",
        (
            ChunkParagraphTaggingInput(
                paragraph,
                existing_candidates=("Major triad",),
            ),
        ),
    )


def _two_paragraph_tagging_request() -> ChunkTaggingRequest:
    paragraphs = (
        ParagraphBlock(
            "document:source:chunk:long-paragraph-reference-1",
            "chunk-01",
            0,
            "A major triad has a root, third, and fifth.",
        ),
        ParagraphBlock(
            "document:source:chunk:long-paragraph-reference-2",
            "chunk-01",
            1,
            "A minor triad lowers the third.",
        ),
    )
    return ChunkTaggingRequest(
        "chunk-01",
        tuple(ChunkParagraphTaggingInput(paragraph) for paragraph in paragraphs),
    )


@pytest.mark.anyio
async def test_structured_chunk_tagger_maps_provider_output_to_domain_result() -> None:
    provider = _StructuredProvider(
        {
            "chunk_tagging_and_conflict": {
                "chunk_id": "chunk-01",
                "chunk_new_concepts": [],
                "paragraphs": [
                    {
                        "paragraph_ref": "p1",
                        "labels": [
                            {
                                "generated_concept": "Major chord",
                                "action": "reuse_existing",
                                "resolved_concept": "Major triad",
                                "roles": ["Definition"],
                            }
                        ],
                        "tagging_status": "completed",
                    }
                ],
            }
        }
    )

    result = await StructuredChunkTagger(provider).tag(_tagging_request())

    assert result.paragraphs[0].labels[0].roles == (ContentRole.DEFINITION,)
    assert result.paragraphs[0].paragraph_ref == "paragraph-1"
    call = provider.calls[0]
    assert call["task_type"] == "chunk_tagging_and_conflict"
    assert '"paragraph_ref": "p1"' in call["user_prompt"]
    assert '"paragraph_ref": "paragraph-1"' not in call["user_prompt"]
    assert "A major triad has a root, third, and fifth." in call["user_prompt"]


@pytest.mark.anyio
async def test_structured_chunk_tagger_exposes_complete_nested_json_schema() -> None:
    provider = _StructuredProvider(
        {
            "chunk_tagging_and_conflict": {
                "chunk_id": "chunk-01",
                "chunk_new_concepts": [],
                "paragraphs": [
                    {
                        "paragraph_ref": "p1",
                        "labels": [],
                        "tagging_status": "completed",
                    }
                ],
            }
        }
    )

    await StructuredChunkTagger(provider).tag(_tagging_request())

    schema = provider.calls[0]["response_model"].model_json_schema()
    paragraph_schema = schema["properties"]["paragraphs"]["items"]
    assert paragraph_schema["additionalProperties"] is False
    assert paragraph_schema["required"] == [
        "paragraph_ref",
        "labels",
        "tagging_status",
    ]
    assert paragraph_schema["properties"]["tagging_status"] == {
        "type": "string",
        "const": "completed",
    }
    label_schema = paragraph_schema["properties"]["labels"]["items"]
    assert label_schema["additionalProperties"] is False
    assert label_schema["required"] == [
        "generated_concept",
        "action",
        "resolved_concept",
        "roles",
    ]
    assert label_schema["properties"]["action"]["enum"] == [
        "reuse_existing",
        "reuse_chunk_new",
        "create_new",
    ]
    assert label_schema["properties"]["roles"]["items"]["enum"] == [
        role.value for role in ContentRole
    ]


@pytest.mark.anyio
async def test_structured_chunk_prompt_contains_few_shot_contract_examples() -> None:
    provider = _StructuredProvider(
        {
            "chunk_tagging_and_conflict": {
                "chunk_id": "chunk-01",
                "chunk_new_concepts": [],
                "paragraphs": [
                    {
                        "paragraph_ref": "p1",
                        "labels": [],
                        "tagging_status": "completed",
                    }
                ],
            }
        }
    )

    await StructuredChunkTagger(provider).tag(_tagging_request())

    prompt = json.loads(provider.calls[0]["user_prompt"])
    assert prompt["instructions"]["response_format"] == "json_object"
    assert prompt["instructions"]["paragraph_keys"] == [
        "paragraph_ref",
        "labels",
        "tagging_status",
    ]
    assert prompt["instructions"]["label_keys"] == [
        "generated_concept",
        "action",
        "resolved_concept",
        "roles",
    ]
    assert prompt["instructions"]["copy_example_ids"] is False
    assert len(prompt["few_shot_examples"]) == 2
    assert prompt["few_shot_examples"][0]["output"]["paragraphs"][0] == {
        "paragraph_ref": "p1",
        "labels": [
            {
                "generated_concept": "Major chord",
                "action": "reuse_existing",
                "resolved_concept": "Major triad",
                "roles": ["Definition"],
            }
        ],
        "tagging_status": "completed",
    }
    assert prompt["request"]["chunk_id"] == "chunk-01"
    assert prompt["request"]["paragraphs"][0]["paragraph_ref"] == "p1"


@pytest.mark.anyio
async def test_structured_chunk_tagger_maps_each_alias_back_to_its_original_ref() -> None:
    provider = _StructuredProvider(
        {
            "chunk_tagging_and_conflict": {
                "chunk_id": "chunk-01",
                "chunk_new_concepts": [],
                "paragraphs": [
                    {
                        "paragraph_ref": "p2",
                        "labels": [],
                        "tagging_status": "completed",
                    },
                    {
                        "paragraph_ref": "p1",
                        "labels": [],
                        "tagging_status": "completed",
                    },
                ],
            }
        }
    )

    result = await StructuredChunkTagger(provider).tag(
        _two_paragraph_tagging_request()
    )

    prompt = json.loads(provider.calls[0]["user_prompt"])
    assert [item["paragraph_ref"] for item in prompt["request"]["paragraphs"]] == [
        "p1",
        "p2",
    ]
    assert [paragraph.paragraph_ref for paragraph in result.paragraphs] == [
        "document:source:chunk:long-paragraph-reference-2",
        "document:source:chunk:long-paragraph-reference-1",
    ]
    assert "long-paragraph-reference" not in provider.calls[0]["user_prompt"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("returned_refs", "error"),
    [
        (("p1",), "exactly match request aliases"),
        (("p1", "p3"), "unknown paragraph alias: p3"),
        (("p1", "p1"), "duplicate paragraph alias: p1"),
    ],
)
async def test_structured_chunk_tagger_rejects_invalid_returned_aliases(
    returned_refs: tuple[str, ...],
    error: str,
) -> None:
    provider = _StructuredProvider(
        {
            "chunk_tagging_and_conflict": {
                "chunk_id": "chunk-01",
                "chunk_new_concepts": [],
                "paragraphs": [
                    {
                        "paragraph_ref": paragraph_ref,
                        "labels": [],
                        "tagging_status": "completed",
                    }
                    for paragraph_ref in returned_refs
                ],
            }
        }
    )

    with pytest.raises(ValueError, match=error):
        await StructuredChunkTagger(provider).tag(_two_paragraph_tagging_request())


@pytest.mark.anyio
async def test_structured_role_selector_uses_markdown_and_validates_candidates() -> None:
    provider = _StructuredProvider(
        {
            "concept_role_selection": {
                "selections": [
                    {
                        "concept": "Major triad",
                        "selected_roles": ["Definition"],
                        "selection_rank": 1,
                    }
                ]
            }
        }
    )
    selector = StructuredConceptRoleSelector(provider)
    request = ConceptRoleSelectionRequest(
        "What is a major triad?",
        (
            ConceptRoleCandidate(
                "Major triad",
                (ContentRole.DEFINITION, ContentRole.EXAMPLE),
                ("chunk-01",),
            ),
        ),
    )

    result = await selector.select(request)

    assert result.selections[0].concept == "Major triad"
    assert result.selections[0].selected_roles == (ContentRole.DEFINITION,)
    assert "# Concept and Role Selection" in provider.calls[0]["user_prompt"]
    assert "### Concept: Major triad" in provider.calls[0]["user_prompt"]


@pytest.mark.anyio
async def test_structured_role_selector_rejects_foreign_concept() -> None:
    provider = _StructuredProvider(
        {
            "concept_role_selection": {
                "selections": [
                    {
                        "concept": "Invented concept",
                        "selected_roles": ["Definition"],
                        "selection_rank": 1,
                    }
                ]
            }
        }
    )
    selector = StructuredConceptRoleSelector(provider)
    request = ConceptRoleSelectionRequest(
        "What is a major triad?",
        (ConceptRoleCandidate("Major triad", (ContentRole.DEFINITION,)),),
    )

    with pytest.raises(ValueError, match="present in candidates"):
        await selector.select(request)
