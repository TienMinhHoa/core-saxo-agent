"""Evidence-selection adapters shared by the future agent graph.

The retrieval package owns the provider-specific selectors and traversal logic.
This module gives the agent boundary one request/result shape for both
selection strategies while keeping every selected paragraph inside the
document-search candidate set.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from saxophone.retrieval.paragraph_selection import (
    ParagraphSelectionRequest,
    StructuredParagraphSelector,
    build_paragraph_choices,
)
from saxophone.retrieval.paragraph_traversal import ParagraphTraversal
from saxophone.retrieval.renderers import (
    AnswerContextModel,
    ConceptInventoryBuilder,
    SelectedConceptRole,
    SourceParagraph,
)
from saxophone.retrieval.role_selection import (
    ConceptRoleCandidate,
    ConceptRoleSelectionRequest,
    ConceptRoleSelectionResult,
    StructuredConceptRoleSelector,
)
from saxophone.tagging.models import ParagraphConceptRole

from .contracts import AgentQuestion, SelectionStrategy
from .document_search import DocumentSearchResult


@dataclass(frozen=True, slots=True, init=False)
class SelectionRequest:
    """Question plus the typed candidates returned by document search.

    ``search_result`` is the canonical field.  ``document_result`` and
    ``candidates`` are accepted as keyword aliases during migration so callers
    do not need to know which name an older adapter used.
    """

    question: str
    search_result: DocumentSearchResult
    filters: Mapping[str, str]

    def __init__(
        self,
        question: AgentQuestion | str,
        search_result: DocumentSearchResult | None = None,
        *,
        document_result: DocumentSearchResult | None = None,
        candidates: DocumentSearchResult | None = None,
    ) -> None:
        if isinstance(question, AgentQuestion):
            question_text = question.question
            filters: Mapping[str, str] = question.filters
        elif isinstance(question, str) and question.strip():
            question_text = question.strip()
            filters = MappingProxyType({})
        else:
            raise ValueError("question must be an AgentQuestion or non-blank string")

        supplied = [value for value in (search_result, document_result, candidates) if value is not None]
        if len(supplied) != 1:
            raise ValueError("exactly one document search result is required")
        result = supplied[0]
        if not isinstance(result, DocumentSearchResult):
            raise ValueError("search result must be a DocumentSearchResult")

        object.__setattr__(self, "question", question_text)
        object.__setattr__(self, "search_result", result)
        object.__setattr__(self, "filters", MappingProxyType(dict(filters)))

    @property
    def document_result(self) -> DocumentSearchResult:
        """Compatibility alias for the canonical search result."""

        return self.search_result

    @property
    def candidates(self) -> DocumentSearchResult:
        """Compatibility alias used by early graph prototypes."""

        return self.search_result

    @property
    def agent_question(self) -> AgentQuestion:
        """Recreate the normalized agent question for downstream tools."""

        return AgentQuestion(self.question, filters=self.filters)


@dataclass(frozen=True, slots=True)
class SelectionResult:
    """Common, validated output of either evidence-selection strategy."""

    strategy: SelectionStrategy | str
    answer_context: AnswerContextModel
    reasons: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        strategy = _coerce_strategy(self.strategy)
        if not isinstance(self.answer_context, AnswerContextModel):
            raise ValueError("answer_context must be an AnswerContextModel")
        context = self.answer_context
        paragraph_refs = tuple(paragraph.paragraph_ref for paragraph in context.paragraphs)
        if len(set(paragraph_refs)) != len(paragraph_refs):
            raise ValueError("selected paragraphs must have unique refs")
        explicit_refs = context.selected_paragraph_refs
        if len(set(explicit_refs)) != len(explicit_refs):
            raise ValueError("selected paragraph refs must be unique")
        if any(ref not in paragraph_refs for ref in explicit_refs):
            raise ValueError("selected paragraph refs must reference selected paragraphs")
        for selection in context.selected_roles:
            for ref in selection.paragraph_refs:
                if ref not in paragraph_refs:
                    raise ValueError("selected role contains a dangling paragraph ref")

        normalized_reasons: list[tuple[str, str]] = []
        seen_reason_refs: set[str] = set()
        for item in self.reasons:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("reasons must contain (paragraph_ref, reason) pairs")
            ref, reason = item
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError("reason paragraph ref must not be blank")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("selection reason must not be blank")
            normalized_ref = ref.strip()
            if normalized_ref in seen_reason_refs:
                raise ValueError("selection reasons must have unique paragraph refs")
            if normalized_ref not in paragraph_refs:
                raise ValueError("selection reason must reference a selected paragraph")
            seen_reason_refs.add(normalized_ref)
            normalized_reasons.append((normalized_ref, reason.strip()))

        object.__setattr__(self, "strategy", strategy)
        object.__setattr__(self, "reasons", tuple(normalized_reasons))

    @property
    def context(self) -> AnswerContextModel:
        """Short alias used by orchestration code."""

        return self.answer_context

    @property
    def selected_strategy(self) -> SelectionStrategy:
        """Ledger-friendly name for the chosen strategy."""

        return self.strategy

    @property
    def paragraphs(self) -> tuple[SourceParagraph, ...]:
        return self.answer_context.paragraphs

    @property
    def selected_paragraphs(self) -> tuple[SourceParagraph, ...]:
        return self.answer_context.paragraphs

    @property
    def selected_paragraph_refs(self) -> tuple[str, ...]:
        if self.answer_context.selected_paragraph_refs:
            return self.answer_context.selected_paragraph_refs
        refs: list[str] = []
        for selection in self.answer_context.selected_roles:
            for ref in selection.paragraph_refs:
                if ref not in refs:
                    refs.append(ref)
        return tuple(refs)

    @property
    def paragraph_refs(self) -> tuple[str, ...]:
        """Compatibility alias for callers that use the shorter name."""

        return self.selected_paragraph_refs

    @property
    def selected_roles(self) -> tuple[SelectedConceptRole, ...]:
        return self.answer_context.selected_roles

    @property
    def reason_by_paragraph(self) -> Mapping[str, str]:
        return MappingProxyType(dict(self.reasons))

    def validate_against(self, request: SelectionRequest) -> None:
        """Reject any result that escapes the document-search candidate scope."""

        if not isinstance(request, SelectionRequest):
            raise ValueError("request must be a SelectionRequest")
        candidates = request.search_result.paragraph_candidates
        candidate_by_ref = {paragraph.paragraph_ref: paragraph for paragraph in candidates}
        selected_refs = self.selected_paragraph_refs
        if any(ref not in candidate_by_ref for ref in selected_refs):
            raise ValueError("selected paragraph is outside candidate scope")

        hit_chunks = {hit.chunk_ref for hit in request.search_result.hits}
        for paragraph in self.paragraphs:
            if paragraph.chunk_id and hit_chunks and paragraph.chunk_id not in hit_chunks:
                raise ValueError("selected paragraph is outside retrieved candidate scope")


class ParagraphDirectSelector:
    """Adapt the existing structured paragraph selector to the agent port."""

    strategy = SelectionStrategy.PARAGRAPH_DIRECT

    def __init__(
        self,
        selector: Any = None,
        *,
        provider: Any = None,
    ) -> None:
        dependency = selector if selector is not None else provider
        if dependency is None:
            raise TypeError("selector or provider is required")
        if callable(getattr(dependency, "generate_structured", None)):
            dependency = StructuredParagraphSelector(dependency)
        if not callable(getattr(dependency, "select", None)):
            raise TypeError("selector must provide select")
        self._selector = dependency

    async def select(self, request: SelectionRequest) -> SelectionResult:
        _require_request(request)
        paragraphs = request.search_result.paragraph_candidates
        if not paragraphs or not request.search_result.hits:
            return _empty_result(self.strategy)

        choices = build_paragraph_choices(paragraphs)
        selection_request = ParagraphSelectionRequest(request.question, choices)
        selected = await self._selector.select(selection_request)
        if not hasattr(selected, "selections"):
            raise ValueError("paragraph selector must return a selection result")
        selections = tuple(selected.selections)
        choices_by_key = {choice.key: choice for choice in choices}
        selected_paragraphs: list[SourceParagraph] = []
        selected_refs: list[str] = []
        reasons: list[tuple[str, str]] = []
        seen_keys: set[str] = set()
        for selection in selections:
            key = getattr(selection, "key", None)
            reason = getattr(selection, "reason", None)
            choice = choices_by_key.get(key)
            if choice is None:
                raise ValueError("selected paragraph key must be present in candidate scope")
            if key in seen_keys:
                raise ValueError("selected paragraph keys must be unique")
            seen_keys.add(key)
            if choice.paragraph_ref not in selected_refs:
                selected_refs.append(choice.paragraph_ref)
                selected_paragraphs.append(choice.paragraph)
                if isinstance(reason, str) and reason.strip():
                    reasons.append((choice.paragraph_ref, reason))

        result = SelectionResult(
            self.strategy,
            AnswerContextModel((), tuple(selected_paragraphs), tuple(selected_refs)),
            tuple(reasons),
        )
        result.validate_against(request)
        return result


class ConceptRoleSelector:
    """Adapt concept-role selection and paragraph traversal to the agent port."""

    strategy = SelectionStrategy.CONCEPT_ROLE

    def __init__(
        self,
        selector: Any = None,
        *,
        role_selector: Any = None,
        provider: Any = None,
        inventory_builder: ConceptInventoryBuilder | None = None,
        traversal: ParagraphTraversal | None = None,
    ) -> None:
        dependencies = [value for value in (selector, role_selector, provider) if value is not None]
        if len(dependencies) != 1:
            raise TypeError("exactly one selector, role_selector, or provider is required")
        dependency = dependencies[0]
        if callable(getattr(dependency, "generate_structured", None)):
            dependency = StructuredConceptRoleSelector(dependency)
        if not callable(getattr(dependency, "select", None)):
            raise TypeError("role selector must provide select")
        self._selector = dependency
        self._inventory_builder = inventory_builder or ConceptInventoryBuilder()
        self._traversal = traversal or ParagraphTraversal()

    async def select(self, request: SelectionRequest) -> SelectionResult:
        _require_request(request)
        search_result = request.search_result
        if (
            not search_result.hits
            or not search_result.relations
            or not search_result.paragraph_candidates
        ):
            return _empty_result(self.strategy)

        paragraph_by_ref = {
            paragraph.paragraph_ref: paragraph
            for paragraph in search_result.paragraph_candidates
        }
        hit_chunks = {hit.chunk_ref for hit in search_result.hits}
        scoped_relations = _scope_relations(
            search_result.relations,
            paragraph_by_ref,
            hit_chunks,
        )
        if not scoped_relations:
            return _empty_result(self.strategy)

        paragraph_chunks = {
            ref: (paragraph.chunk_id or paragraph.parent_header)
            for ref, paragraph in paragraph_by_ref.items()
        }
        chunk_ranks = _chunk_ranks(search_result)
        inventory = self._inventory_builder.build(
            scoped_relations,
            paragraph_chunks=paragraph_chunks,
            chunk_ranks=chunk_ranks,
        )
        if not inventory.concepts:
            return _empty_result(self.strategy)

        candidates = tuple(
            ConceptRoleCandidate(
                item.concept,
                tuple(role.role for role in item.available_roles),
                tuple(chunk.chunk_id for chunk in item.parent_chunks),
            )
            for item in inventory.concepts
        )
        role_request = ConceptRoleSelectionRequest(request.question, candidates)
        selected = await self._selector.select(role_request)
        if not isinstance(selected, ConceptRoleSelectionResult):
            raise ValueError("role selector must return ConceptRoleSelectionResult")
        selected.validate_against(role_request)
        if not selected.selections:
            return _empty_result(self.strategy)

        inventory_by_concept = {item.concept: item for item in inventory.concepts}
        selected_roles = tuple(
            SelectedConceptRole(
                selection.concept,
                role.value,
                (),
                inventory_by_concept[selection.concept].parent_chunks,
            )
            for selection in selected.selections
            for role in selection.selected_roles
        )
        context = self._traversal.resolve(
            selected_roles,
            scoped_relations,
            paragraph_by_ref,
        )
        result = SelectionResult(self.strategy, context)
        result.validate_against(request)
        return result


def adapt_legacy_selector(selector: Any) -> ParagraphDirectSelector | ConceptRoleSelector:
    """Wrap pre-agent selectors without branching in the retrieval service."""

    if selector is None:
        raise TypeError("selector is required")
    if isinstance(selector, (ParagraphDirectSelector, ConceptRoleSelector)):
        return selector
    if isinstance(selector, StructuredParagraphSelector):
        return ParagraphDirectSelector(selector)
    return ConceptRoleSelector(selector)


def _empty_result(strategy: SelectionStrategy) -> SelectionResult:
    return SelectionResult(strategy, AnswerContextModel((), (), ()))


def _require_request(request: object) -> None:
    if not isinstance(request, SelectionRequest):
        raise ValueError("request must be a SelectionRequest")


def _coerce_strategy(value: SelectionStrategy | str) -> SelectionStrategy:
    if isinstance(value, SelectionStrategy):
        return value
    try:
        return SelectionStrategy(value)
    except (TypeError, ValueError) as error:
        raise ValueError("strategy has an unsupported value") from error


def _chunk_ranks(result: DocumentSearchResult) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for hit in result.hits:
        current = ranks.get(hit.chunk_ref)
        if current is None or hit.rank < current:
            ranks[hit.chunk_ref] = hit.rank
    return ranks


def _scope_relations(
    relations: tuple[ParagraphConceptRole, ...],
    paragraphs: Mapping[str, SourceParagraph],
    hit_chunks: set[str],
) -> tuple[ParagraphConceptRole, ...]:
    scoped: list[ParagraphConceptRole] = []
    for relation in relations:
        paragraph = paragraphs.get(relation.paragraph_id)
        if paragraph is None:
            raise ValueError("relation references a missing paragraph candidate")
        chunk = paragraph.chunk_id or paragraph.parent_header
        if hit_chunks and chunk not in hit_chunks:
            raise ValueError("relation references a paragraph outside candidate scope")
        scoped.append(relation)
    return tuple(scoped)
