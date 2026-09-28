"""Application orchestration for concept-role question retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping, Protocol

from saxophone.tagging.models import ParagraphConceptRole

from .context_limiter import ContextLimiter
from .models import ChunkHit
from .ports import ChunkRetriever
from .renderers import (
    AnswerContextMarkdownRenderer,
    SourceParagraph,
)
from .sqlite_context import RetrievalContext

if TYPE_CHECKING:
    from saxophone.agent.document_search import DocumentSearchResult
    from saxophone.agent.evidence_selection import SelectionRequest


class RetrievalContextRepository(Protocol):
    async def load_for_hits(self, hits: tuple[ChunkHit, ...]) -> RetrievalContext: ...


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
    answer_context: object | None = None


class QuestionRetrievalService:
    """Coordinate retrieval, role selection, traversal, limiting, and rendering."""

    def __init__(
        self,
        *,
        retriever: ChunkRetriever,
        selector: object,
        relations: tuple[ParagraphConceptRole, ...] = (),
        paragraphs: Mapping[str, SourceParagraph] | None = None,
        context_repository: RetrievalContextRepository | None = None,
        limiter: ContextLimiter | None = None,
        max_paragraphs: int = 20,
        max_tokens: int = 4000,
    ) -> None:
        from saxophone.agent.evidence_selection import adapt_legacy_selector

        self._retriever = retriever
        self._selector = adapt_legacy_selector(selector)
        if context_repository is not None and not callable(
            getattr(context_repository, "load_for_hits", None)
        ):
            raise TypeError("context_repository must provide load_for_hits")
        self._relations = tuple(relations)
        self._paragraphs = dict(paragraphs or {})
        self._context_repository = context_repository
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

        relations = self._relations
        paragraphs = self._paragraphs
        if self._context_repository is not None:
            hydrated = await self._context_repository.load_for_hits(hits)
            if not isinstance(hydrated, RetrievalContext):
                raise TypeError("context_repository must return RetrievalContext")
            relations = hydrated.relations
            paragraphs = dict(hydrated.paragraphs)

        chunk_ranks = {hit.chunk_ref: hit.rank for hit in hits}
        paragraph_chunks = {
            ref: (paragraph.chunk_id or paragraph.parent_header)
            for ref, paragraph in paragraphs.items()
        }
        relations = tuple(
            relation for relation in relations
            if paragraph_chunks.get(relation.paragraph_id) in chunk_ranks
        )
        candidate_paragraphs = tuple(
            paragraph
            for ref, paragraph in paragraphs.items()
            if paragraph_chunks.get(ref) in chunk_ranks
        )
        candidate_refs = {paragraph.paragraph_ref for paragraph in candidate_paragraphs}
        from saxophone.agent.document_search import DocumentSearchResult
        from saxophone.agent.evidence_selection import SelectionRequest

        search_result = DocumentSearchResult(
            query=request.question,
            hits=hits,
            paragraph_candidates=candidate_paragraphs,
            relations=tuple(
                relation
                for relation in relations
                if relation.paragraph_id in candidate_refs
            ),
        )
        selection_result = await self._selector.select(
            SelectionRequest(request.question, search_result)
        )
        if not selection_result.selected_paragraph_refs:
            return RetrievalBundle(
                RetrievalBundleStatus.NO_RELEVANT_CONCEPT_ROLE,
                request.question,
                hits,
            )
        context = self._limiter.limit(
            selection_result.answer_context,
            max_paragraphs=request.max_paragraphs,
            max_tokens=request.max_tokens,
        )
        markdown = AnswerContextMarkdownRenderer().render_answer_context(request.question, context)
        return RetrievalBundle(
            RetrievalBundleStatus.READY,
            request.question,
            hits,
            markdown,
            context,
        )
