"""Application orchestration for concept-role question retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from saxophone.tagging.models import ParagraphConceptRole

from .context_limiter import ContextLimiter
from .models import ChunkHit
from .paragraph_traversal import ParagraphTraversal
from .ports import ChunkRetriever
from .renderers import (
    AnswerContextMarkdownRenderer,
    ConceptInventoryBuilder,
    SelectedConceptRole,
    SourceParagraph,
)
from .role_selection import (
    ConceptRoleCandidate,
    ConceptRoleSelectionRequest,
    ConceptRoleSelector,
)


class RetrievalBundleStatus(str, Enum):
    READY = "ready"
    NO_RETRIEVAL_CONTEXT = "no_retrieval_context"
    NO_RELEVANT_CONCEPT_ROLE = "no_relevant_concept_role"


@dataclass(frozen=True, slots=True)
class QuestionRequest:
    question: str
    filters: Mapping[str, object] | None = None
    chunk_limit: int = 10
    max_paragraphs: int = 20
    max_tokens: int = 4000

    def __post_init__(self) -> None:
        if not isinstance(self.question, str) or not self.question.strip():
            raise ValueError("question must not be blank")
        if isinstance(self.chunk_limit, bool) or not isinstance(self.chunk_limit, int) or self.chunk_limit < 1:
            raise ValueError("chunk_limit must be positive")
        for name in ("max_paragraphs", "max_tokens"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be positive")
        if not isinstance(self.filters, (Mapping, type(None))):
            raise ValueError("filters must be a mapping or None")
        object.__setattr__(self, "question", self.question.strip())
        if self.filters is not None:
            object.__setattr__(self, "filters", MappingProxyType(dict(self.filters)))


@dataclass(frozen=True, slots=True)
class RetrievalBundle:
    status: RetrievalBundleStatus
    question: str
    hits: tuple[ChunkHit, ...] = ()
    answer_context_markdown: str | None = None


class QuestionRetrievalService:
    """Coordinate retrieval, role selection, traversal, limiting, and rendering."""

    def __init__(
        self,
        *,
        retriever: ChunkRetriever,
        selector: ConceptRoleSelector,
        relations: tuple[ParagraphConceptRole, ...],
        paragraphs: Mapping[str, SourceParagraph],
        limiter: ContextLimiter | None = None,
        max_paragraphs: int = 20,
        max_tokens: int = 4000,
    ) -> None:
        self._retriever = retriever
        self._selector = selector
        self._relations = tuple(relations)
        self._paragraphs = dict(paragraphs)
        self._limiter = limiter or ContextLimiter()
        self._max_paragraphs = max_paragraphs
        self._max_tokens = max_tokens

    async def retrieve(self, request: QuestionRequest) -> RetrievalBundle:
        if not isinstance(request, QuestionRequest):
            raise ValueError("request must be a QuestionRequest")
        hits = tuple(await self._retriever.search(
            request.question,
            filters=request.filters,
            limit=request.chunk_limit,
        ))
        if not hits:
            return RetrievalBundle(RetrievalBundleStatus.NO_RETRIEVAL_CONTEXT, request.question)

        chunk_ranks = {hit.chunk_ref: hit.rank for hit in hits}
        paragraph_chunks = {
            ref: (paragraph.chunk_id or paragraph.parent_header)
            for ref, paragraph in self._paragraphs.items()
        }
        relations = tuple(
            relation for relation in self._relations
            if paragraph_chunks.get(relation.paragraph_id) in chunk_ranks
        )
        inventory = ConceptInventoryBuilder().build(
            relations,
            paragraph_chunks=paragraph_chunks,
            chunk_ranks=chunk_ranks,
        ) if relations else None
        if inventory is None or not inventory.concepts:
            return RetrievalBundle(RetrievalBundleStatus.NO_RELEVANT_CONCEPT_ROLE, request.question, hits)

        candidates = tuple(
            ConceptRoleCandidate(
                item.concept,
                tuple(role.role for role in item.available_roles),
                tuple(chunk.chunk_id for chunk in item.parent_chunks),
            )
            for item in inventory.concepts
        )
        selection_request = ConceptRoleSelectionRequest(request.question, candidates)
        selection_result = await self._selector.select(selection_request)
        selection_result.validate_against(selection_request)
        if not selection_result.selections:
            return RetrievalBundle(RetrievalBundleStatus.NO_RELEVANT_CONCEPT_ROLE, request.question, hits)

        selected = tuple(
            SelectedConceptRole(
                selection.concept,
                role.value,
                (),
                tuple(
                    next(
                        item.parent_chunks
                        for item in inventory.concepts
                        if item.concept == selection.concept
                    )
                ),
            )
            for selection in selection_result.selections
            for role in selection.selected_roles
        )
        context = ParagraphTraversal().resolve(selected, relations, self._paragraphs)
        context = self._limiter.limit(
            context,
            max_paragraphs=request.max_paragraphs,
            max_tokens=request.max_tokens,
        )
        markdown = AnswerContextMarkdownRenderer().render_answer_context(request.question, context)
        return RetrievalBundle(RetrievalBundleStatus.READY, request.question, hits, markdown)
