"""Document-search adapter for the agent orchestration boundary.

The adapter keeps the existing vector search and SQLite hydration services in
place while exposing one typed result to the future agent graph.  It stops at
candidate discovery: evidence selection and answer synthesis belong to later
agent stages.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from saxophone.documents.policies import is_safe_relative_image_reference
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.ports import ChunkRetriever
from saxophone.retrieval.renderers import SourceParagraph
from saxophone.retrieval.sqlite_context import RetrievalContext
from saxophone.tagging.models import ParagraphConceptRole

from .contracts import AgentQuestion


class DocumentSearchStatus(StrEnum):
    """Outcome of searching and hydrating document candidates."""

    READY = "ready"
    NO_HITS = "no_hits"
    NO_CONTEXT = "no_context"


@dataclass(frozen=True, slots=True)
class DocumentSearchResult:
    """Typed document candidates available to the agent's next stage."""

    query: str
    hits: tuple[ChunkHit, ...] = ()
    paragraph_candidates: tuple[SourceParagraph, ...] = ()
    relations: tuple[ParagraphConceptRole, ...] = ()
    pages: tuple[str, ...] = ()
    image_refs: tuple[str, ...] = ()
    confidence: float | None = None
    status: DocumentSearchStatus | str | None = None

    def __post_init__(self) -> None:
        query = _normalize_text("query", self.query)
        hits = _require_tuple_of("hits", self.hits, ChunkHit)
        paragraphs = _require_tuple_of(
            "paragraph_candidates", self.paragraph_candidates, SourceParagraph
        )
        relations = _require_tuple_of(
            "relations", self.relations, ParagraphConceptRole
        )
        pages = _require_unique_text_tuple("pages", self.pages)
        image_refs = _require_unique_text_tuple("image_refs", self.image_refs)
        for image_ref in image_refs:
            if not is_safe_relative_image_reference(image_ref):
                raise ValueError("image_refs must contain safe relative references")

        hit_keys = tuple((hit.source_ref, hit.chunk_ref, hit.retrieval_version) for hit in hits)
        if len(set(hit_keys)) != len(hit_keys):
            raise ValueError("hits must not contain duplicate chunk scopes")
        paragraph_refs = tuple(paragraph.paragraph_ref for paragraph in paragraphs)
        if len(set(paragraph_refs)) != len(paragraph_refs):
            raise ValueError("paragraph_candidates must contain unique paragraph refs")
        relation_keys = tuple(
            (relation.paragraph_id, relation.canonical_concept, relation.content_role.value)
            for relation in relations
        )
        if len(set(relation_keys)) != len(relation_keys):
            raise ValueError("relations must be unique")
        if any(relation.paragraph_id not in paragraph_refs for relation in relations):
            raise ValueError("relations must reference paragraph candidates")

        confidence = self.confidence
        if confidence is not None:
            if (
                isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence)
                or not 0 <= confidence <= 1
            ):
                raise ValueError("confidence must be a finite number between 0 and 1")
            confidence = float(confidence)

        status = self.status
        if status is None:
            status = (
                DocumentSearchStatus.NO_HITS
                if not hits
                else DocumentSearchStatus.READY
                if paragraphs
                else DocumentSearchStatus.NO_CONTEXT
            )
        elif not isinstance(status, DocumentSearchStatus):
            try:
                status = DocumentSearchStatus(status)
            except (TypeError, ValueError) as error:
                raise ValueError("status has an unsupported value") from error

        if status is DocumentSearchStatus.NO_HITS and hits:
            raise ValueError("no_hits status requires an empty hit set")
        if status is DocumentSearchStatus.NO_CONTEXT and (not hits or paragraphs):
            raise ValueError("no_context status requires hits without paragraphs")
        if status is DocumentSearchStatus.READY and (not hits or not paragraphs):
            raise ValueError("ready status requires hits and paragraph candidates")

        object.__setattr__(self, "query", query)
        object.__setattr__(self, "hits", hits)
        object.__setattr__(self, "paragraph_candidates", paragraphs)
        object.__setattr__(self, "relations", relations)
        object.__setattr__(self, "pages", pages)
        object.__setattr__(self, "image_refs", image_refs)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "status", status)

    @property
    def paragraphs(self) -> tuple[SourceParagraph, ...]:
        """Compatibility alias for callers that use the shorter field name."""

        return self.paragraph_candidates

    @property
    def source_paragraphs(self) -> tuple[SourceParagraph, ...]:
        """Return the hydrated paragraph candidates by their source name."""

        return self.paragraph_candidates

    @property
    def chunk_hits(self) -> tuple[ChunkHit, ...]:
        """Compatibility alias for callers that name hits explicitly."""

        return self.hits

    @property
    def concept_roles(self) -> tuple[ParagraphConceptRole, ...]:
        """Return hydrated concept-role facts for the candidate paragraphs."""

        return self.relations

    @property
    def concept_role_relations(self) -> tuple[ParagraphConceptRole, ...]:
        """Return concept-role facts using the full field name."""

        return self.relations

    @property
    def page_refs(self) -> tuple[str, ...]:
        """Return the distinct page labels represented by the candidates."""

        return self.pages


class RetrievalContextLoader(Protocol):
    """Small protocol for the SQLite hydration dependency."""

    async def load_for_hits(self, hits: Sequence[ChunkHit]) -> RetrievalContext:
        """Hydrate paragraphs and concept-role relations for ranked hits."""


class SemanticDocumentSearchTool:
    """Adapt semantic chunk retrieval and SQLite hydration into one tool."""

    name = "document_search"

    def __init__(
        self,
        retriever: ChunkRetriever,
        context_repository: RetrievalContextLoader,
        *,
        max_hits: int = 20,
    ) -> None:
        if not callable(getattr(retriever, "search", None)):
            raise TypeError("retriever must provide search")
        if not callable(getattr(context_repository, "load_for_hits", None)):
            raise TypeError("context_repository must provide load_for_hits")
        if isinstance(max_hits, bool) or not isinstance(max_hits, int) or max_hits < 1:
            raise ValueError("max_hits must be a positive integer")
        self._retriever = retriever
        self._context_repository = context_repository
        self._max_hits = max_hits

    async def search(
        self,
        question: AgentQuestion,
        budget: Any = None,
    ) -> DocumentSearchResult:
        """Search chunks and hydrate their paragraph candidates.

        ``budget`` is accepted at this boundary so the tool can be injected
        into the shared agent port now; budget accounting is introduced by the
        dedicated RunBudget task without changing this contract.
        """

        del budget
        if not isinstance(question, AgentQuestion):
            raise ValueError("question must be an AgentQuestion")

        raw_hits = await self._retriever.search(
            question.question,
            filters=dict(question.filters),
            limit=self._max_hits,
        )
        hits = _normalize_hits(raw_hits)
        if not hits:
            return DocumentSearchResult(
                query=question.question,
                status=DocumentSearchStatus.NO_HITS,
            )

        context = await self._context_repository.load_for_hits(hits)
        if not isinstance(context, RetrievalContext):
            raise TypeError("context_repository must return RetrievalContext")
        paragraphs = tuple(context.paragraphs.values())
        _validate_candidate_scope(hits, paragraphs)
        relations = tuple(context.relations)
        pages = _collect_pages(paragraphs)
        if not pages:
            pages = _collect_hit_pages(hits)
        image_refs = _collect_image_refs(paragraphs)
        image_refs = _merge_image_refs(image_refs, _collect_hit_image_refs(hits))
        status = (
            DocumentSearchStatus.READY
            if paragraphs
            else DocumentSearchStatus.NO_CONTEXT
        )
        return DocumentSearchResult(
            query=question.question,
            hits=hits,
            paragraph_candidates=paragraphs,
            relations=relations,
            pages=pages,
            image_refs=image_refs,
            confidence=_confidence(hits),
            status=status,
        )

    async def run(self, request: object, budget: Any = None) -> DocumentSearchResult:
        """Expose the common named-tool shape used by the agent registry."""

        if not isinstance(request, AgentQuestion):
            raise ValueError("request must be an AgentQuestion")
        return await self.search(request, budget)


# Explicit aliases keep the adapter name descriptive while allowing the
# composition root to use the shorter service vocabulary during migration.
DocumentSearchToolAdapter = SemanticDocumentSearchTool
DocumentSearchService = SemanticDocumentSearchTool
DocumentSearchTool = SemanticDocumentSearchTool


def _normalize_hits(value: object) -> tuple[ChunkHit, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("retriever must return a sequence of ChunkHit values")
    hits = tuple(value)
    if any(not isinstance(hit, ChunkHit) for hit in hits):
        raise ValueError("retriever must return ChunkHit values")
    return hits


def _validate_candidate_scope(
    hits: tuple[ChunkHit, ...], paragraphs: tuple[SourceParagraph, ...]
) -> None:
    hit_chunks = {hit.chunk_ref for hit in hits}
    for paragraph in paragraphs:
        if paragraph.chunk_id and paragraph.chunk_id not in hit_chunks:
            raise ValueError("paragraph candidate is outside retrieved chunk scope")


def _collect_pages(paragraphs: tuple[SourceParagraph, ...]) -> tuple[str, ...]:
    pages: list[str] = []
    for paragraph in paragraphs:
        for page in paragraph.pages:
            if not isinstance(page, str) or not page.strip():
                raise ValueError("paragraph pages must contain non-blank strings")
            normalized = page.strip()
            if normalized not in pages:
                pages.append(normalized)
    return tuple(pages)


def _collect_image_refs(paragraphs: tuple[SourceParagraph, ...]) -> tuple[str, ...]:
    refs: list[str] = []
    for paragraph in paragraphs:
        for image_ref in paragraph.image_refs:
            if image_ref not in refs:
                refs.append(image_ref)
    return tuple(refs)


def _collect_hit_pages(hits: tuple[ChunkHit, ...]) -> tuple[str, ...]:
    pages: list[str] = []
    for hit in hits:
        for key in ("page_start", "page_end"):
            value = hit.metadata.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                continue
            page = str(value)
            if page not in pages:
                pages.append(page)
    return tuple(pages)


def _collect_hit_image_refs(hits: tuple[ChunkHit, ...]) -> tuple[str, ...]:
    refs: list[str] = []
    for hit in hits:
        value = hit.metadata.get("image_refs", ())
        values = (value,) if isinstance(value, str) else value
        if not isinstance(values, (list, tuple)):
            continue
        for image_ref in values:
            if isinstance(image_ref, str) and image_ref.strip() and image_ref not in refs:
                refs.append(image_ref)
    return tuple(refs)


def _merge_image_refs(*groups: tuple[str, ...]) -> tuple[str, ...]:
    refs: list[str] = []
    for group in groups:
        for image_ref in group:
            if image_ref not in refs:
                refs.append(image_ref)
    return tuple(refs)


def _confidence(hits: tuple[ChunkHit, ...]) -> float | None:
    scores: list[float] = []
    for hit in hits:
        for attribute in ("fused_score", "semantic_score", "keyword_score"):
            score = getattr(hit, attribute)
            if score is not None:
                scores.append(float(score))
                break
    if not scores:
        return None
    return max(0.0, min(1.0, max(scores)))


def _normalize_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")
    return value.strip()


def _require_tuple_of(name: str, value: object, item_type: type) -> tuple:
    if not isinstance(value, tuple):
        raise ValueError(f"{name} must be a tuple")
    if any(not isinstance(item, item_type) for item in value):
        raise ValueError(f"{name} must contain {item_type.__name__} values")
    return value


def _require_unique_text_tuple(name: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{name} must be a tuple")
    normalized = tuple(_normalize_text(f"{name} item", item) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must be unique")
    return normalized
