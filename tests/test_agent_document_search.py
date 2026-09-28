from __future__ import annotations

from dataclasses import dataclass

import pytest

from saxophone.agent.contracts import AgentQuestion, BudgetExhaustedError, RunBudget
from saxophone.agent.document_search import (
    DocumentSearchResult,
    DocumentSearchStatus,
    SemanticDocumentSearchTool,
)
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.renderers import SourceParagraph
from saxophone.retrieval.sqlite_context import RetrievalContext
from saxophone.tagging.models import ContentRole, ParagraphConceptRole


def _hit(
    chunk_ref: str = "chunk-1",
    *,
    score: float = 0.91,
    document_ref: str = "music-book",
) -> ChunkHit:
    return ChunkHit(
        source_ref="music-theory.md",
        chunk_ref=chunk_ref,
        rank=1,
        retrieval_version="retrieval-v1",
        metadata={
            "document_ref": document_ref,
            "source_version": "source-v1",
        },
        semantic_score=score,
    )


def _paragraph(
    paragraph_ref: str = "paragraph-1",
    *,
    image_refs: tuple[str, ...] = ("images/figure-1.png",),
) -> SourceParagraph:
    return SourceParagraph(
        paragraph_ref=paragraph_ref,
        source="music-theory.md",
        parent_header="Major triads",
        nested_headings=("Definitions",),
        text="A major triad has a root, third, and fifth.",
        concepts_and_roles=("Major triad -> Definition",),
        pages=("121", "122"),
        image_refs=image_refs,
        chunk_id="chunk-1",
    )


@dataclass
class _FakeRetriever:
    hits: tuple[ChunkHit, ...]

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, object, int]] = []

    async def search(self, query: str, *, filters=None, limit: int = 10):
        self.calls.append((query, filters, limit))
        return self.hits


class _FakeContextRepository:
    def __init__(self, context: RetrievalContext) -> None:
        self.context = context
        self.calls: list[tuple[ChunkHit, ...]] = []

    async def load_for_hits(self, hits: tuple[ChunkHit, ...]) -> RetrievalContext:
        self.calls.append(hits)
        return self.context


@pytest.mark.anyio
async def test_document_search_returns_hydrated_candidates_without_selecting_evidence() -> None:
    hit = _hit()
    relation = ParagraphConceptRole("paragraph-1", "Major triad", ContentRole.DEFINITION)
    context = RetrievalContext((relation,), {"paragraph-1": _paragraph()})
    retriever = _FakeRetriever((hit,))
    repository = _FakeContextRepository(context)
    tool = SemanticDocumentSearchTool(retriever, repository)

    result = await tool.search(
        AgentQuestion("  What is a major triad?  ", filters={"source": "music.md"}),
        object(),
    )

    assert isinstance(result, DocumentSearchResult)
    assert result.status is DocumentSearchStatus.READY
    assert result.query == "What is a major triad?"
    assert result.hits == (hit,)
    assert result.paragraph_candidates == (_paragraph(),)
    assert result.relations == (relation,)
    assert result.pages == ("121", "122")
    assert result.image_refs == ("images/figure-1.png",)
    assert result.confidence == pytest.approx(0.91)
    assert retriever.calls == [("What is a major triad?", {"source": "music.md"}, 20)]
    assert repository.calls == [(hit,)]


@pytest.mark.anyio
async def test_document_search_preserves_paragraphs_when_relations_are_missing() -> None:
    hit = _hit()
    paragraph = _paragraph(image_refs=())
    retriever = _FakeRetriever((hit,))
    repository = _FakeContextRepository(RetrievalContext((), {"paragraph-1": paragraph}))

    result = await SemanticDocumentSearchTool(retriever, repository).search(
        AgentQuestion("What is a major triad?"), object()
    )

    assert result.status is DocumentSearchStatus.READY
    assert result.paragraph_candidates == (paragraph,)
    assert result.relations == ()
    assert result.image_refs == ()


@pytest.mark.anyio
async def test_document_search_reports_no_hits_without_hydrating_context() -> None:
    retriever = _FakeRetriever(())
    repository = _FakeContextRepository(RetrievalContext((), {}))

    result = await SemanticDocumentSearchTool(retriever, repository).search(
        AgentQuestion("unknown"), object()
    )

    assert result.status is DocumentSearchStatus.NO_HITS
    assert result.hits == ()
    assert result.paragraph_candidates == ()
    assert result.confidence is None
    assert repository.calls == []


@pytest.mark.anyio
async def test_document_search_reports_hits_without_hydrated_context() -> None:
    hit = _hit()
    retriever = _FakeRetriever((hit,))
    repository = _FakeContextRepository(RetrievalContext((), {}))

    result = await SemanticDocumentSearchTool(retriever, repository).search(
        AgentQuestion("What is a major triad?"), object()
    )

    assert result.status is DocumentSearchStatus.NO_CONTEXT
    assert result.hits == (hit,)
    assert result.paragraph_candidates == ()
    assert result.confidence == pytest.approx(0.91)


@pytest.mark.anyio
async def test_document_search_tool_run_delegates_to_search() -> None:
    hit = _hit()
    retriever = _FakeRetriever((hit,))
    repository = _FakeContextRepository(RetrievalContext((), {_paragraph().paragraph_ref: _paragraph()}))
    tool = SemanticDocumentSearchTool(retriever, repository)

    result = await tool.run(AgentQuestion("What is a major triad?"), object())

    assert result.hits == (hit,)


@pytest.mark.anyio
async def test_document_search_consumes_shared_budget_and_applies_hit_limit() -> None:
    hit = _hit()
    retriever = _FakeRetriever((hit,))
    repository = _FakeContextRepository(
        RetrievalContext((), {_paragraph().paragraph_ref: _paragraph()})
    )
    tool = SemanticDocumentSearchTool(retriever, repository, max_hits=20)
    budget = RunBudget(max_tool_calls=1, max_document_search_calls=1, max_hits_per_tool=1)

    await tool.search(AgentQuestion("What is a major triad?"), budget)

    assert retriever.calls[0][2] == 1
    assert budget.snapshot().document_search_calls == 1
    with pytest.raises(BudgetExhaustedError):
        await tool.search(AgentQuestion("What is a major triad?"), budget)
    assert len(retriever.calls) == 1


def test_document_search_result_derives_status_for_direct_dto_construction() -> None:
    hit = _hit()
    result = DocumentSearchResult(query="question", hits=(hit,))

    assert result.status is DocumentSearchStatus.NO_CONTEXT
    assert result.confidence is None


@pytest.mark.anyio
async def test_document_search_rejects_unsafe_hydrated_image_reference() -> None:
    hit = _hit()
    paragraph = _paragraph(image_refs=("../secret.png",))
    repository = _FakeContextRepository(RetrievalContext((), {paragraph.paragraph_ref: paragraph}))

    with pytest.raises(ValueError, match="image"):
        await SemanticDocumentSearchTool(_FakeRetriever((hit,)), repository).search(
            AgentQuestion("What is a major triad?"), object()
        )


@pytest.mark.anyio
async def test_document_search_rejects_invalid_question_or_retriever_output() -> None:
    tool = SemanticDocumentSearchTool(
        _FakeRetriever(("not-a-hit",)),
        _FakeContextRepository(RetrievalContext((), {})),
    )

    with pytest.raises(ValueError, match="question"):
        await tool.search("What is a major triad?", object())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="ChunkHit"):
        await tool.search(AgentQuestion("What is a major triad?"), object())
