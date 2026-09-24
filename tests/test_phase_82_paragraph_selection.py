from __future__ import annotations

import pytest

from saxophone.retrieval.paragraph_selection import (
    ParagraphSelectionRequest,
    ParagraphSelectionResult,
    StructuredParagraphSelector,
    build_paragraph_choices,
    render_paragraph_choices,
)
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.question_retrieval import (
    QuestionRequest,
    QuestionRetrievalService,
    RetrievalBundleStatus,
)
from saxophone.retrieval.sqlite_context import RetrievalContext
from saxophone.retrieval.renderers import (
    AnswerContextMarkdownRenderer,
    AnswerContextModel,
    ParentChunk,
    SelectedConceptRole,
    SourceParagraph,
)
from saxophone.tagging.models import ContentRole, ParagraphConceptRole


def _paragraph(
    ref: str,
    *,
    source: str = "music.md",
    text: str = "Harmony organizes simultaneous sounds.",
    concepts: tuple[str, ...] = ("Harmony -> Definition",),
    pages: tuple[str, ...] = (),
    images: tuple[str, ...] = (),
) -> SourceParagraph:
    return SourceParagraph(
        ref,
        source,
        "Harmony",
        ("Music theory",),
        text,
        concepts,
        pages,
        images,
        "chunk-01",
    )


def test_build_paragraph_choices_deduplicates_refs_and_merges_metadata() -> None:
    choices = build_paragraph_choices(
        (
            _paragraph("p-1", concepts=("Harmony -> Definition",), pages=("10",)),
            _paragraph(
                "p-1",
                source="music-theory.md",
                concepts=("Harmony -> Explanation",),
                pages=("11",),
                images=("figure-10",),
            ),
            _paragraph("p-2", text="Chord progressions connect harmonies."),
        )
    )

    assert tuple(choice.key for choice in choices) == ("1", "2")
    assert tuple(choice.paragraph_ref for choice in choices) == ("p-1", "p-2")
    merged = choices[0].paragraph
    assert merged.source == "music-theory.md"
    assert merged.pages == ("10", "11")
    assert merged.image_refs == ("figure-10",)
    assert merged.concepts_and_roles == (
        "Harmony -> Definition",
        "Harmony -> Explanation",
    )


def test_build_paragraph_choices_deduplicates_exact_text_across_refs() -> None:
    choices = build_paragraph_choices(
        (
            _paragraph("p-1", pages=("10",)),
            _paragraph("p-2", pages=("20",), images=("figure-20",)),
        )
    )

    assert tuple(choice.key for choice in choices) == ("1",)
    assert choices[0].paragraph_ref == "p-1"
    assert choices[0].paragraph.pages == ("10", "20")
    assert choices[0].paragraph.image_refs == ("figure-20",)


def test_render_paragraph_choices_uses_key_value_lines_and_preserves_metadata() -> None:
    choices = build_paragraph_choices(
        (_paragraph("p-1", pages=("10",), images=("figure-10",)),)
    )

    rendered = render_paragraph_choices("Explain harmony", choices)

    assert "1: Harmony" in rendered
    assert "Paragraph ref: p-1" in rendered
    assert "Pages: 10" in rendered
    assert "Images: figure-10" in rendered
    assert "Harmony organizes simultaneous sounds." in rendered


class _Provider:
    structured_output_mode = "json_object"

    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs["response_model"].model_validate(self.response)


@pytest.mark.anyio
async def test_structured_paragraph_selector_returns_reason_before_key() -> None:
    provider = _Provider(
        {
            "selections": [
                {"reason": "This paragraph explains harmony.", "key": "1"}
            ]
        }
    )
    selector = StructuredParagraphSelector(provider)
    request = ParagraphSelectionRequest(
        "Explain harmony",
        build_paragraph_choices((_paragraph("p-1"), _paragraph("p-2"))),
    )

    result = await selector.select(request)

    assert result.selections[0].reason == "This paragraph explains harmony."
    assert result.selections[0].key == "1"
    prompt = provider.calls[0]["user_prompt"]
    assert "1: Harmony" in prompt
    assert "Return exactly one JSON object" in prompt
    assert "reason" in prompt and "key" in prompt


def test_paragraph_selection_schema_is_minimal_and_ordered() -> None:
    schema = ParagraphSelectionResult.model_json_schema()
    item = schema["properties"]["selections"]["items"]

    assert item["required"] == ["reason", "key"]
    assert item["additionalProperties"] is False
    assert list(item["properties"]) == ["reason", "key"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [
        {"selections": [{"reason": "first", "key": "1"}, {"reason": "duplicate", "key": "1"}]},
        {"selections": [{"reason": "unknown", "key": "99"}]},
        {"selections": [{"reason": "", "key": "1"}]},
        {"selections": [{"reason": "extra", "key": "1", "extra": True}]},
    ],
)
async def test_structured_paragraph_selector_rejects_invalid_selection_contract(
    response: object,
) -> None:
    provider = _Provider(response)
    selector = StructuredParagraphSelector(provider)
    request = ParagraphSelectionRequest(
        "Explain harmony",
        build_paragraph_choices((_paragraph("p-1"), _paragraph("p-2"))),
    )

    with pytest.raises(ValueError):
        await selector.select(request)


def test_answer_context_renders_duplicate_paragraph_once_after_role_overlap() -> None:
    paragraph = _paragraph("p-1")
    context = AnswerContextModel(
        selected_roles=(
            SelectedConceptRole("Harmony", "Definition", ("p-1",), (ParentChunk("chunk-01", 1),)),
            SelectedConceptRole("Harmony", "Explanation", ("p-1",), (ParentChunk("chunk-01", 1),)),
        ),
        paragraphs=(paragraph,),
    )

    rendered = AnswerContextMarkdownRenderer().render_answer_context(
        "Explain harmony", context
    )

    assert rendered.count("Harmony organizes simultaneous sounds.") == 1


class _Retriever:
    async def search(self, query: str, *, filters=None, limit: int = 10):
        return [
            ChunkHit(
                "music.md",
                "chunk-01",
                1,
                "topic-v1",
                {"document_ref": "music-book", "source_version": "source-v1"},
                semantic_score=0.9,
            )
        ]


class _ContextRepository:
    async def load_for_hits(self, hits):
        paragraph = _paragraph("p-1")
        return RetrievalContext(
            (
                ParagraphConceptRole("p-1", "Harmony", ContentRole.DEFINITION),
                ParagraphConceptRole("p-1", "Harmony", ContentRole.EXPLANATION),
            ),
            {"p-1": paragraph},
        )


@pytest.mark.anyio
async def test_question_retrieval_maps_numbered_selection_to_unique_paragraph_ref() -> None:
    selector = StructuredParagraphSelector(
        _Provider(
            {
                "selections": [
                    {"reason": "This paragraph explains harmony.", "key": "1"}
                ]
            }
        )
    )
    service = QuestionRetrievalService(
        retriever=_Retriever(),
        selector=selector,
        context_repository=_ContextRepository(),
    )

    result = await service.retrieve(QuestionRequest("Explain harmony"))

    assert result.status is RetrievalBundleStatus.READY
    assert result.answer_context is not None
    assert result.answer_context.selected_paragraph_refs == ("p-1",)
    assert tuple(item.paragraph_ref for item in result.answer_context.paragraphs) == ("p-1",)
    assert result.answer_context_markdown is not None
    assert result.answer_context_markdown.count("Harmony organizes simultaneous sounds.") == 1
