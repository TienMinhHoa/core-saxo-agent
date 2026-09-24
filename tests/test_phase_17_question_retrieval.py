"""TDD contract for the internal question-retrieval orchestration service."""

from __future__ import annotations

import asyncio

import pytest

from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.question_retrieval import (
    QuestionRequest,
    QuestionRetrievalService,
    RetrievalBundleStatus,
)
from saxophone.retrieval.renderers import SourceParagraph
from saxophone.retrieval.role_selection import (
    ConceptRoleSelection,
    ConceptRoleSelectionResult,
)
from saxophone.tagging.models import ContentRole, ParagraphConceptRole


class _Retriever:
    def __init__(self, hits: list[ChunkHit]) -> None:
        self.hits = hits
        self.calls: list[tuple[str, object, int]] = []

    async def search(self, query: str, *, filters=None, limit: int = 10) -> list[ChunkHit]:
        self.calls.append((query, filters, limit))
        return self.hits


class _Selector:
    def __init__(self, result: ConceptRoleSelectionResult) -> None:
        self.result = result
        self.requests = []

    async def select(self, request):
        self.requests.append(request)
        return self.result


def _hit() -> ChunkHit:
    return ChunkHit(
        "music.md",
        "chunk-01",
        1,
        "retrieval-v1",
        {"document": "A major triad has a root, third, and fifth."},
        semantic_score=0.9,
    )


def _service(retriever: _Retriever, selector: _Selector) -> QuestionRetrievalService:
    relation = ParagraphConceptRole("p-1", "Major triad", ContentRole.DEFINITION)
    paragraph = SourceParagraph(
        "p-1", "music.md", "Major and Minor Triads", (),
        "A major triad has a root, third, and fifth.", (), (), (), "chunk-01",
    )
    return QuestionRetrievalService(
        retriever=retriever,
        selector=selector,
        relations=(relation,),
        paragraphs={"p-1": paragraph},
    )


def test_question_request_rejects_blank_question_before_provider_calls() -> None:
    with pytest.raises(ValueError, match="question"):
        QuestionRequest("   ")


def test_retrieve_returns_no_context_without_calling_role_selector() -> None:
    retriever = _Retriever([])
    selector = _Selector(ConceptRoleSelectionResult(()))

    result = asyncio.run(_service(retriever, selector).retrieve(QuestionRequest("What is a major triad?")))

    assert result.status is RetrievalBundleStatus.NO_RETRIEVAL_CONTEXT
    assert result.answer_context_markdown is None
    assert selector.requests == []


def test_retrieve_orchestrates_candidate_context_into_validated_markdown() -> None:
    retriever = _Retriever([_hit()])
    selector = _Selector(
        ConceptRoleSelectionResult((
            ConceptRoleSelection("Major triad", (ContentRole.DEFINITION,), 1),
        ))
    )

    result = asyncio.run(
        _service(retriever, selector).retrieve(
            QuestionRequest("  What is a major triad?  ", filters={"source": "music.md"})
        )
    )

    assert result.status is RetrievalBundleStatus.READY
    assert retriever.calls == [("What is a major triad?", {"source": "music.md"}, 10)]
    assert selector.requests[0].question == "What is a major triad?"
    assert result.answer_context_markdown is not None
    assert "### [1]" in result.answer_context_markdown
