from __future__ import annotations

import pytest

from saxophone.agent.contracts import SelectionStrategy
from saxophone.agent.document_search import DocumentSearchResult
from saxophone.agent.evidence_selection import (
    ConceptRoleSelector,
    ParagraphDirectSelector,
    SelectionRequest,
    SelectionResult,
)
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.paragraph_selection import (
    ParagraphSelectionResult,
    StructuredParagraphSelector,
)
from saxophone.retrieval.renderers import AnswerContextModel, SourceParagraph
from saxophone.retrieval.role_selection import (
    ConceptRoleSelection,
    ConceptRoleSelectionResult,
)
from saxophone.tagging.models import ContentRole, ParagraphConceptRole


def _hit(chunk_ref: str = "chunk-1", rank: int = 1) -> ChunkHit:
    return ChunkHit(
        "music.md",
        chunk_ref,
        rank,
        "retrieval-v1",
        {"document_ref": "music-book", "source_version": "source-v1"},
        semantic_score=0.9,
    )


def _paragraph(ref: str, chunk: str = "chunk-1", text: str | None = None) -> SourceParagraph:
    return SourceParagraph(
        ref,
        "music.md",
        "Major triads",
        (),
        text or f"Text for {ref}.",
        ("Major triad -> Definition",),
        ("121",),
        (),
        chunk,
    )


def _search_result(
    paragraphs: tuple[SourceParagraph, ...],
    relations: tuple[ParagraphConceptRole, ...] = (),
) -> DocumentSearchResult:
    return DocumentSearchResult(
        query="What is a major triad?",
        hits=(_hit(),),
        paragraph_candidates=paragraphs,
        relations=relations,
    )


class _ParagraphProvider:
    structured_output_mode = "json_object"

    async def generate_structured(self, **kwargs: object) -> ParagraphSelectionResult:
        return kwargs["response_model"].model_validate(
            {"selections": [{"reason": "directly answers the question", "key": "1"}]}
        )


class _RoleSelector:
    def __init__(self, result: ConceptRoleSelectionResult) -> None:
        self.result = result
        self.requests: list[object] = []

    async def select(self, request: object) -> ConceptRoleSelectionResult:
        self.requests.append(request)
        return self.result


@pytest.mark.anyio
async def test_paragraph_direct_selector_returns_shared_result_for_candidates() -> None:
    paragraphs = (_paragraph("p-1"), _paragraph("p-2", text="Another paragraph."))
    selector = ParagraphDirectSelector(StructuredParagraphSelector(_ParagraphProvider()))

    result = await selector.select(SelectionRequest("What is a major triad?", _search_result(paragraphs)))

    assert isinstance(result, SelectionResult)
    assert result.strategy is SelectionStrategy.PARAGRAPH_DIRECT
    assert result.selected_paragraph_refs == ("p-1",)
    assert result.paragraphs == (paragraphs[0],)
    assert result.answer_context.selected_paragraph_refs == ("p-1",)


@pytest.mark.anyio
async def test_paragraph_direct_selector_can_select_without_relations() -> None:
    paragraph = _paragraph("p-1")
    result = await ParagraphDirectSelector(StructuredParagraphSelector(_ParagraphProvider())).select(
        SelectionRequest("What is a major triad?", _search_result((paragraph,)))
    )

    assert result.selected_paragraph_refs == ("p-1",)


class _ForeignParagraphSelector:
    async def select(self, request: object) -> object:
        return type(
            "Result",
            (),
            {"selections": (type("Selection", (), {"key": "99", "reason": "foreign"})(),)},
        )()


@pytest.mark.anyio
async def test_paragraph_direct_selector_rejects_selection_outside_candidate_scope() -> None:
    selector = ParagraphDirectSelector(_ForeignParagraphSelector())

    with pytest.raises(ValueError, match="candidate"):
        await selector.select(SelectionRequest("question", _search_result((_paragraph("p-1"),))))


@pytest.mark.anyio
async def test_concept_role_selector_returns_same_result_shape_and_traverses_scope() -> None:
    relation = ParagraphConceptRole("p-1", "Major triad", ContentRole.DEFINITION)
    paragraph = _paragraph("p-1")
    role_selector = _RoleSelector(
        ConceptRoleSelectionResult(
            (ConceptRoleSelection("Major triad", (ContentRole.DEFINITION,), 1),)
        )
    )
    selector = ConceptRoleSelector(role_selector)

    result = await selector.select(
        SelectionRequest("What is a major triad?", _search_result((paragraph,), (relation,)))
    )

    assert result.strategy is SelectionStrategy.CONCEPT_ROLE
    assert result.selected_paragraph_refs == ("p-1",)
    assert result.selected_roles[0].paragraph_refs == ("p-1",)
    assert len(role_selector.requests) == 1


@pytest.mark.anyio
async def test_concept_role_selector_returns_empty_result_without_relations() -> None:
    role_selector = _RoleSelector(ConceptRoleSelectionResult(()))
    result = await ConceptRoleSelector(role_selector).select(
        SelectionRequest("question", _search_result((_paragraph("p-1"),)))
    )

    assert result.strategy is SelectionStrategy.CONCEPT_ROLE
    assert result.selected_paragraph_refs == ()
    assert role_selector.requests == []


def test_selection_result_rejects_paragraph_outside_request_scope() -> None:
    request = SelectionRequest("question", _search_result((_paragraph("p-1"),)))
    outside = _paragraph("outside")
    with pytest.raises(ValueError, match="candidate"):
        SelectionResult(
            SelectionStrategy.PARAGRAPH_DIRECT,
            AnswerContextModel((), (outside,), ("outside",)),
        ).validate_against(request)
