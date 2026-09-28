"""Validated, immutable contracts shared by the agent orchestration layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
from urllib.parse import urlsplit

from saxophone.documents.policies import is_safe_relative_image_reference


class SelectionStrategy(StrEnum):
    """Evidence selection strategy chosen by the main agent."""

    PARAGRAPH_DIRECT = "paragraph_direct"
    CONCEPT_ROLE = "concept_role"


class EvidenceSourceType(StrEnum):
    """Source categories that may be cited by an agent run."""

    DOCUMENT = "document"
    WEB = "web"


class AgentOutcome(StrEnum):
    """Terminal statuses exposed by the agent boundary."""

    ANSWERED = "answered"
    NEEDS_CLARIFICATION = "needs_clarification"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    BUDGET_EXHAUSTED = "budget_exhausted"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AgentQuestion:
    """Normalized user question and retrieval constraints."""

    question: str
    filters: Mapping[str, str] = field(default_factory=dict)
    context_limit: int = 12_000

    def __post_init__(self) -> None:
        question = _normalize_text("question", self.question)
        if isinstance(self.filters, Mapping):
            normalized_filters: dict[str, str] = {}
            for key, value in self.filters.items():
                normalized_key = _normalize_text("filter key", key)
                normalized_value = _normalize_text("filter value", value)
                if normalized_key in normalized_filters:
                    raise ValueError("filters must contain unique keys")
                normalized_filters[normalized_key] = normalized_value
        else:
            raise ValueError("filters must be a mapping")
        _require_positive_int("context_limit", self.context_limit)
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "filters", MappingProxyType(normalized_filters))


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """A single source fragment that can be placed in an evidence ledger."""

    evidence_id: str
    source_type: EvidenceSourceType
    chunk: str = ""
    paragraph: str = ""
    text: str = ""
    page: int | None = None
    image_refs: tuple[str, ...] = ()
    source_ref: str | None = None
    url: str | None = None
    retrieved_at: str | None = None

    def __post_init__(self) -> None:
        evidence_id = _normalize_identifier("evidence_id", self.evidence_id)
        source_type = _coerce_enum(EvidenceSourceType, "source_type", self.source_type)
        chunk = _normalize_optional_identifier_value("chunk", self.chunk)
        paragraph = _normalize_optional_identifier_value("paragraph", self.paragraph)
        text = _normalize_text("text", self.text, strip=False)
        if self.page is not None and (
            isinstance(self.page, bool) or not isinstance(self.page, int) or self.page < 1
        ):
            raise ValueError("page must be a positive integer")
        if not isinstance(self.image_refs, tuple):
            raise ValueError("image_refs must be a tuple")
        if len(set(self.image_refs)) != len(self.image_refs):
            raise ValueError("image_refs must be unique")
        for image_ref in self.image_refs:
            if not is_safe_relative_image_reference(image_ref):
                raise ValueError("unsafe image reference")
        source_ref = _optional_identifier("source_ref", self.source_ref)
        url = _optional_url("url", self.url)
        retrieved_at = _optional_text("retrieved_at", self.retrieved_at)

        if source_type is EvidenceSourceType.DOCUMENT:
            if not chunk or not paragraph or self.page is None:
                raise ValueError("document evidence requires chunk, paragraph, and page")
        elif source_type is EvidenceSourceType.WEB:
            if url is None or retrieved_at is None:
                raise ValueError("web evidence requires url and retrieved_at")

        object.__setattr__(self, "evidence_id", evidence_id)
        object.__setattr__(self, "source_type", source_type)
        object.__setattr__(self, "chunk", chunk)
        object.__setattr__(self, "paragraph", paragraph)
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "source_ref", source_ref)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "retrieved_at", retrieved_at)

    @property
    def chunk_id(self) -> str:
        """Compatibility alias used by retrieval adapters."""

        return self.chunk

    @property
    def paragraph_ref(self) -> str:
        """Compatibility alias used by paragraph-oriented adapters."""

        return self.paragraph

    @property
    def page_start(self) -> int | None:
        """Return the single page represented by this first-task contract."""

        return self.page

    @property
    def page_end(self) -> int | None:
        """Return the single page represented by this first-task contract."""

        return self.page


@dataclass(frozen=True, slots=True)
class Citation:
    """A user-visible label pointing at one ledger evidence item."""

    evidence_id: str
    label: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _normalize_identifier("evidence_id", self.evidence_id))
        object.__setattr__(self, "label", _normalize_text("label", self.label))


@dataclass(frozen=True, slots=True)
class SearchTrace:
    """Small, safe summary of one search step; prompt contents are excluded."""

    tool: str
    query_count: int = 1
    hit_count: int = 0
    status: str = "completed"

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool", _normalize_identifier("tool", self.tool))
        object.__setattr__(self, "status", _normalize_identifier("status", self.status))
        _require_non_negative_int("query_count", self.query_count)
        _require_non_negative_int("hit_count", self.hit_count)


@dataclass(frozen=True, slots=True)
class EvidenceLedger:
    """Immutable evidence selected for one agent run."""

    run_id: str
    question: str | AgentQuestion
    selected_strategy: SelectionStrategy
    evidence: tuple[EvidenceItem, ...] = ()
    search_trace: tuple[SearchTrace, ...] = ()
    normalized_queries: tuple[str, ...] = ()
    used_evidence_ids: tuple[str, ...] = ()
    citations: tuple[Citation, ...] = ()
    image_evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        run_id = _normalize_identifier("run_id", self.run_id)
        question = self.question.question if isinstance(self.question, AgentQuestion) else _normalize_text("question", self.question)
        selected_strategy = _coerce_enum(
            SelectionStrategy,
            "selected_strategy",
            self.selected_strategy,
        )
        evidence = _require_tuple_of("evidence", self.evidence, EvidenceItem)
        search_trace = _require_tuple_of("search_trace", self.search_trace, SearchTrace)
        normalized_queries = _require_unique_text_tuple("normalized_queries", self.normalized_queries)
        used_evidence_ids = _require_unique_identifier_tuple(
            "used_evidence_ids", self.used_evidence_ids
        )
        citations = _require_tuple_of("citations", self.citations, Citation)
        image_evidence_ids = _require_unique_identifier_tuple(
            "image_evidence_ids", self.image_evidence_ids
        )

        evidence_by_id = {item.evidence_id: item for item in evidence}
        if len(evidence_by_id) != len(evidence):
            raise ValueError("evidence IDs must be unique")
        for evidence_id in used_evidence_ids:
            if evidence_id not in evidence_by_id:
                raise ValueError("used evidence must reference existing evidence")
        for citation in citations:
            if citation.evidence_id not in evidence_by_id:
                raise ValueError("citation must reference existing evidence")
        for evidence_id in image_evidence_ids:
            item = evidence_by_id.get(evidence_id)
            if item is None:
                raise ValueError("image evidence must reference existing evidence")
            if not item.image_refs:
                raise ValueError("image evidence must reference evidence with images")

        labels = [citation.label for citation in citations]
        if len(set(labels)) != len(labels):
            raise ValueError("citation labels must be unique")

        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "selected_strategy", selected_strategy)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "search_trace", search_trace)
        object.__setattr__(self, "normalized_queries", normalized_queries)
        object.__setattr__(self, "used_evidence_ids", used_evidence_ids)
        object.__setattr__(self, "citations", citations)
        object.__setattr__(self, "image_evidence_ids", image_evidence_ids)


@dataclass(frozen=True, slots=True)
class ClarificationRequest:
    """Question and bounded choices shown when evidence has competing meanings."""

    question: str
    options: tuple[str, ...]
    reason_code: str

    def __post_init__(self) -> None:
        question = _normalize_text("question", self.question)
        options = _require_unique_text_tuple("options", self.options)
        if not options:
            raise ValueError("options must not be empty")
        reason_code = _normalize_identifier("reason_code", self.reason_code)
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "options", options)
        object.__setattr__(self, "reason_code", reason_code)


def _coerce_enum(enum_type: type[StrEnum], name: str, value: object) -> StrEnum:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError as exc:
            raise ValueError(f"{name} has an unsupported value") from exc
    raise ValueError(f"{name} must be a {enum_type.__name__}")


def _normalize_text(name: str, value: object, *, strip: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    normalized = value.strip() if strip else value
    if not normalized.strip():
        raise ValueError(f"{name} must not be blank")
    return normalized


def _normalize_identifier(name: str, value: object) -> str:
    normalized = _normalize_text(name, value)
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized):
        raise ValueError(f"{name} must not contain control characters")
    return normalized


def _normalize_optional_identifier_value(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    if not value.strip():
        return ""
    return _normalize_identifier(name, value)


def _optional_identifier(name: str, value: object) -> str | None:
    if value is None:
        return None
    return _normalize_identifier(name, value)


def _optional_text(name: str, value: object) -> str | None:
    if value is None:
        return None
    return _normalize_text(name, value)


def _optional_url(name: str, value: object) -> str | None:
    if value is None:
        return None
    normalized = _normalize_text(name, value)
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{name} must be an absolute HTTP(S) URL")
    return normalized


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_tuple_of(name: str, value: object, item_type: type) -> tuple:
    if not isinstance(value, tuple):
        raise ValueError(f"{name} must be a tuple")
    if any(not isinstance(item, item_type) for item in value):
        raise ValueError(f"{name} must contain {item_type.__name__} values")
    return value


def _require_unique_identifier_tuple(name: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{name} must be a tuple")
    normalized = tuple(_normalize_identifier(f"{name} item", item) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must be unique")
    return normalized


def _require_unique_text_tuple(name: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{name} must be a tuple")
    normalized = tuple(_normalize_text(f"{name} item", item) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must be unique")
    return normalized
