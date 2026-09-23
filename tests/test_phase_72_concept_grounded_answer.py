from __future__ import annotations

import pytest

from saxophone.chat.service import (
    AnswerSource,
    GroundedAnswerResponse,
    GroundedAnswerService,
    GroundedAnswerStatus,
)
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.question_retrieval import (
    QuestionRequest,
    RetrievalBundle,
    RetrievalBundleStatus,
)
from saxophone.retrieval.renderers import (
    AnswerContextModel,
    ParentChunk,
    SelectedConceptRole,
    SourceParagraph,
)
from saxophone.tagging.structured_provider import StructuredOutputMode


def _bundle() -> RetrievalBundle:
    paragraph = SourceParagraph(
        "paragraph-1",
        "music-theory.md",
        "Major triads",
        (),
        "A major triad has a root, third, and fifth.",
        ("Major triad -> Definition",),
        ("121", "122"),
        ("figure-121-01",),
        "chunk-01",
    )
    context = AnswerContextModel(
        (
            SelectedConceptRole(
                "Major triad",
                "Definition",
                ("paragraph-1",),
                (ParentChunk("chunk-01", 1),),
            ),
        ),
        (paragraph,),
    )
    hit = ChunkHit(
        "music-theory.md",
        "chunk-01",
        1,
        "topic-v1",
        {"document_ref": "music-book", "source_version": "source-v1"},
        semantic_score=0.9,
    )
    return RetrievalBundle(
        RetrievalBundleStatus.READY,
        "What is a major triad?",
        (hit,),
        "# Retrieval Context\n\n### [paragraph-1]",
        context,
    )


class _Retrieval:
    def __init__(self, bundle: RetrievalBundle) -> None:
        self.bundle = bundle

    async def retrieve(self, request: QuestionRequest) -> RetrievalBundle:
        return self.bundle


class _StructuredProvider:
    structured_output_mode = StructuredOutputMode.JSON_OBJECT

    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs["response_model"].model_validate(self.response)


@pytest.mark.anyio
async def test_grounded_answer_uses_retrieved_paragraphs_and_returns_typed_sources() -> None:
    provider = _StructuredProvider(
        {
            "answer": "A major triad contains a root, third, and fifth.",
            "used_paragraph_refs": ["paragraph-1"],
        }
    )
    service = GroundedAnswerService(
        retrieval=_Retrieval(_bundle()),
        provider=provider,
        model_version="fake-deepseek",
    )

    result = await service.answer(QuestionRequest("What is a major triad?"))

    assert result == GroundedAnswerResponse(
        status=GroundedAnswerStatus.ANSWERED,
        answer="A major triad contains a root, third, and fifth.",
        sources=(
            AnswerSource(
                paragraph_ref="paragraph-1",
                chunk_id="chunk-01",
                source="music-theory.md",
                page_start=121,
                page_end=122,
                image_refs=("figure-121-01",),
            ),
        ),
        model_version="fake-deepseek",
    )
    assert provider.calls[0]["task_type"] == "answer_generation"
    assert "### [paragraph-1]" in provider.calls[0]["user_prompt"]
    assert provider.calls[0]["response_model"].model_json_schema() == {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer", "used_paragraph_refs"],
        "properties": {
            "answer": {"type": "string", "minLength": 1},
            "used_paragraph_refs": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
            },
        },
    }


@pytest.mark.anyio
async def test_grounded_answer_rejects_reference_outside_retrieval_context() -> None:
    provider = _StructuredProvider(
        {
            "answer": "Unsupported answer.",
            "used_paragraph_refs": ["paragraph-foreign"],
        }
    )
    service = GroundedAnswerService(
        retrieval=_Retrieval(_bundle()),
        provider=provider,
        model_version="fake-deepseek",
    )

    with pytest.raises(ValueError, match="retrieved paragraph context"):
        await service.answer(QuestionRequest("What is a major triad?"))


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            {
                "answer": "A supported answer.",
                "used_paragraph_refs": ["paragraph-1"],
                "unexpected": True,
            },
            "fields",
        ),
        (
            {"answer": " ", "used_paragraph_refs": ["paragraph-1"]},
            "answer",
        ),
        (
            {"answer": "A supported answer.", "used_paragraph_refs": "paragraph-1"},
            "list",
        ),
        (
            {"answer": "A supported answer.", "used_paragraph_refs": [" "]},
            "used_paragraph_refs",
        ),
        (
            {
                "answer": "A supported answer.",
                "used_paragraph_refs": ["paragraph-1", "paragraph-1"],
            },
            "unique",
        ),
    ],
)
async def test_grounded_answer_rejects_invalid_structured_output(
    response: object,
    message: str,
) -> None:
    service = GroundedAnswerService(
        retrieval=_Retrieval(_bundle()),
        provider=_StructuredProvider(response),
        model_version="fake-deepseek",
    )

    with pytest.raises(ValueError, match=message):
        await service.answer(QuestionRequest("What is a major triad?"))


@pytest.mark.anyio
async def test_grounded_answer_preserves_explicit_no_context_status_without_llm_call() -> None:
    provider = _StructuredProvider({})
    bundle = RetrievalBundle(
        RetrievalBundleStatus.NO_RETRIEVAL_CONTEXT,
        "Unknown question",
    )
    service = GroundedAnswerService(
        retrieval=_Retrieval(bundle),
        provider=provider,
        model_version="fake-deepseek",
    )

    result = await service.answer(QuestionRequest("Unknown question"))

    assert result.status is GroundedAnswerStatus.NO_RETRIEVAL_CONTEXT
    assert result.answer is None
    assert result.sources == ()
    assert provider.calls == []
