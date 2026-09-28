"""Validated, immutable contracts shared by the agent orchestration layers."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Lock
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
class BudgetCall:
    """Immutable record of one tool reservation and its terminal status."""

    tool: str
    call_number: int
    status: str = "reserved"
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        tool = _normalize_identifier("tool", self.tool)
        status = _normalize_identifier("status", self.status)
        _require_positive_int("call_number", self.call_number)
        if self.duration_seconds is not None:
            _require_finite_non_negative_float("duration_seconds", self.duration_seconds)
        object.__setattr__(self, "tool", tool)
        object.__setattr__(self, "status", status)


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    """Point-in-time view of the shared limits and their consumption."""

    max_tool_calls: int
    max_document_search_calls: int
    max_web_search_calls: int
    max_hits_per_tool: int
    tool_timeout_seconds: float
    max_context_tokens: int
    tool_calls: int = 0
    document_search_calls: int = 0
    web_search_calls: int = 0
    context_tokens: int = 0
    active_tool_calls: int = 0
    completed_tool_calls: int = 0
    failed_tool_calls: int = 0
    timed_out_tool_calls: int = 0
    calls: tuple[BudgetCall, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "max_tool_calls",
            "max_document_search_calls",
            "max_web_search_calls",
            "max_hits_per_tool",
            "max_context_tokens",
        ):
            _require_positive_int(field_name, getattr(self, field_name))
        _require_finite_positive_float("tool_timeout_seconds", self.tool_timeout_seconds)
        for field_name in (
            "tool_calls",
            "document_search_calls",
            "web_search_calls",
            "context_tokens",
            "active_tool_calls",
            "completed_tool_calls",
            "failed_tool_calls",
            "timed_out_tool_calls",
        ):
            _require_non_negative_int(field_name, getattr(self, field_name))
        if self.tool_calls > self.max_tool_calls:
            raise ValueError("tool_calls must not exceed max_tool_calls")
        if self.document_search_calls > self.max_document_search_calls:
            raise ValueError(
                "document_search_calls must not exceed max_document_search_calls"
            )
        if self.web_search_calls > self.max_web_search_calls:
            raise ValueError("web_search_calls must not exceed max_web_search_calls")
        if self.context_tokens > self.max_context_tokens:
            raise ValueError("context_tokens must not exceed max_context_tokens")
        if self.active_tool_calls > self.tool_calls:
            raise ValueError("active_tool_calls must not exceed tool_calls")
        if self.completed_tool_calls + self.failed_tool_calls > self.tool_calls:
            raise ValueError("terminal tool calls must not exceed tool_calls")
        if self.timed_out_tool_calls > self.failed_tool_calls:
            raise ValueError("timed_out_tool_calls must be failed tool calls")
        if not isinstance(self.calls, tuple) or any(
            not isinstance(call, BudgetCall) for call in self.calls
        ):
            raise ValueError("calls must contain BudgetCall values")

    @property
    def remaining_tool_calls(self) -> int:
        return self.max_tool_calls - self.tool_calls

    remaining_calls = remaining_tool_calls

    @property
    def remaining_document_search_calls(self) -> int:
        return self.max_document_search_calls - self.document_search_calls

    @property
    def remaining_web_search_calls(self) -> int:
        return self.max_web_search_calls - self.web_search_calls

    @property
    def remaining_context_tokens(self) -> int:
        return self.max_context_tokens - self.context_tokens

    @property
    def timeout_count(self) -> int:
        """Compatibility alias used by event and tracing adapters."""

        return self.timed_out_tool_calls

    @property
    def total_tool_calls(self) -> int:
        return self.tool_calls

    @property
    def used_tool_calls(self) -> int:
        return self.tool_calls

    @property
    def used_document_search_calls(self) -> int:
        return self.document_search_calls

    @property
    def used_web_search_calls(self) -> int:
        return self.web_search_calls

    @property
    def used_context_tokens(self) -> int:
        return self.context_tokens

    @property
    def tool_call_trace(self) -> tuple[BudgetCall, ...]:
        return self.calls

    @property
    def exhausted(self) -> bool:
        return (
            self.remaining_tool_calls == 0
            or self.remaining_context_tokens == 0
        )

    def tool_exhausted(self, tool: str) -> bool:
        """Return whether a specific tool can no longer be admitted."""

        normalized_tool = _normalize_identifier("tool", tool)
        if self.exhausted:
            return True
        if normalized_tool == RunBudget.DOCUMENT_SEARCH:
            return self.remaining_document_search_calls == 0
        if normalized_tool == RunBudget.WEB_SEARCH:
            return self.remaining_web_search_calls == 0
        return False


class BudgetExhaustedError(RuntimeError):
    """Raised before a tool runs when the shared run budget is exhausted."""

    def __init__(self, tool: str, snapshot: BudgetSnapshot, reason: str) -> None:
        self.tool = _normalize_identifier("tool", tool)
        self.snapshot = snapshot
        self.reason = _normalize_identifier("reason", reason)
        super().__init__(f"budget exhausted for {self.tool}: {self.reason}")


class RunBudget:
    """Concurrency-safe mutable budget shared by every tool in one run.

    Reservations are atomic and are consumed when a call starts.  A timeout or
    provider failure therefore cannot silently reset the run's limits.
    """

    DOCUMENT_SEARCH = "document_search"
    WEB_SEARCH = "web_search"

    def __init__(
        self,
        max_tool_calls: int = 8,
        max_document_search_calls: int = 3,
        max_web_search_calls: int = 2,
        max_hits_per_tool: int = 20,
        tool_timeout_seconds: float = 20.0,
        max_context_tokens: int = 12_000,
    ) -> None:
        self._validate_limits(
            max_tool_calls=max_tool_calls,
            max_document_search_calls=max_document_search_calls,
            max_web_search_calls=max_web_search_calls,
            max_hits_per_tool=max_hits_per_tool,
            tool_timeout_seconds=tool_timeout_seconds,
            max_context_tokens=max_context_tokens,
        )
        self.max_tool_calls = max_tool_calls
        self.max_document_search_calls = max_document_search_calls
        self.max_web_search_calls = max_web_search_calls
        self.max_hits_per_tool = max_hits_per_tool
        self.tool_timeout_seconds = float(tool_timeout_seconds)
        self.max_context_tokens = max_context_tokens
        self._tool_calls = 0
        self._document_search_calls = 0
        self._web_search_calls = 0
        self._context_tokens = 0
        self._active_tool_calls = 0
        self._completed_tool_calls = 0
        self._failed_tool_calls = 0
        self._timed_out_tool_calls = 0
        self._calls: list[BudgetCall] = []
        self._active_by_tool: dict[str, int] = {}
        self._lock = Lock()

    @classmethod
    def from_settings(cls, settings: object) -> "RunBudget":
        """Build a run budget from the typed application settings boundary."""

        names = (
            "agent_max_tool_calls",
            "agent_max_document_search_calls",
            "agent_max_web_search_calls",
            "agent_max_hits_per_tool",
            "agent_tool_timeout_seconds",
            "agent_max_context_tokens",
        )
        missing = [name for name in names if not hasattr(settings, name)]
        if missing:
            raise TypeError(f"settings is missing budget fields: {', '.join(missing)}")
        return cls(
            max_tool_calls=getattr(settings, names[0]),
            max_document_search_calls=getattr(settings, names[1]),
            max_web_search_calls=getattr(settings, names[2]),
            max_hits_per_tool=getattr(settings, names[3]),
            tool_timeout_seconds=getattr(settings, names[4]),
            max_context_tokens=getattr(settings, names[5]),
        )

    def snapshot(self) -> BudgetSnapshot:
        """Return a detached, immutable view suitable for events and tracing."""

        with self._lock:
            return self._snapshot_locked()

    @property
    def tool_calls(self) -> int:
        return self.snapshot().tool_calls

    @property
    def document_search_calls(self) -> int:
        return self.snapshot().document_search_calls

    @property
    def web_search_calls(self) -> int:
        return self.snapshot().web_search_calls

    @property
    def context_tokens(self) -> int:
        return self.snapshot().context_tokens

    @property
    def trace(self) -> tuple[BudgetCall, ...]:
        """Return the immutable call trace accumulated by this run."""

        with self._lock:
            return tuple(self._calls)

    def can_reserve(self, tool: str) -> bool:
        """Check a tool limit without consuming it."""

        normalized_tool = _normalize_identifier("tool", tool)
        with self._lock:
            return self._reservation_reason_locked(normalized_tool) is None

    # These aliases keep the contract readable at call sites that describe a
    # reservation as a check/consume operation rather than a reservation.
    can_call = can_reserve
    try_reserve = can_reserve

    def reserve(self, tool: str) -> BudgetSnapshot:
        """Atomically consume one tool call or raise ``BudgetExhaustedError``."""

        normalized_tool = _normalize_identifier("tool", tool)
        with self._lock:
            reason = self._reservation_reason_locked(normalized_tool)
            if reason is not None:
                raise BudgetExhaustedError(
                    normalized_tool,
                    self._snapshot_locked(),
                    reason,
                )
            self._tool_calls += 1
            if normalized_tool == self.DOCUMENT_SEARCH:
                self._document_search_calls += 1
            elif normalized_tool == self.WEB_SEARCH:
                self._web_search_calls += 1
            self._active_tool_calls += 1
            self._active_by_tool[normalized_tool] = (
                self._active_by_tool.get(normalized_tool, 0) + 1
            )
            self._calls.append(
                BudgetCall(
                    tool=normalized_tool,
                    call_number=self._tool_calls,
                )
            )
            return self._snapshot_locked()

    consume = reserve

    def complete(
        self,
        tool: str,
        *,
        status: str = "completed",
        duration_seconds: float | None = None,
    ) -> BudgetSnapshot:
        """Close one active call and record its terminal status."""

        normalized_tool = _normalize_identifier("tool", tool)
        normalized_status = _normalize_identifier("status", status)
        if duration_seconds is not None:
            _require_finite_non_negative_float("duration_seconds", duration_seconds)
        with self._lock:
            active = self._active_by_tool.get(normalized_tool, 0)
            if active <= 0:
                raise ValueError(f"no active budget call for {normalized_tool}")
            self._active_by_tool[normalized_tool] = active - 1
            if self._active_by_tool[normalized_tool] == 0:
                del self._active_by_tool[normalized_tool]
            self._active_tool_calls -= 1
            if normalized_status in {"completed", "success"}:
                self._completed_tool_calls += 1
            else:
                self._failed_tool_calls += 1
            if normalized_status == "timeout":
                self._timed_out_tool_calls += 1
            for index in range(len(self._calls) - 1, -1, -1):
                call = self._calls[index]
                if call.tool == normalized_tool and call.status == "reserved":
                    self._calls[index] = BudgetCall(
                        tool=call.tool,
                        call_number=call.call_number,
                        status=normalized_status,
                        duration_seconds=duration_seconds,
                    )
                    break
            return self._snapshot_locked()

    def fail(
        self,
        tool: str,
        *,
        duration_seconds: float | None = None,
    ) -> BudgetSnapshot:
        """Mark an active call failed while keeping its consumed reservation."""

        return self.complete(tool, status="failed", duration_seconds=duration_seconds)

    def timeout(
        self,
        tool: str,
        *,
        duration_seconds: float | None = None,
    ) -> BudgetSnapshot:
        """Mark an active call timed out while keeping its consumed reservation."""

        return self.complete(tool, status="timeout", duration_seconds=duration_seconds)

    def record_context_tokens(self, token_count: int) -> BudgetSnapshot:
        """Consume context-token budget shared by retrieval and synthesis."""

        _require_non_negative_int("token_count", token_count)
        with self._lock:
            if self._context_tokens + token_count > self.max_context_tokens:
                raise BudgetExhaustedError(
                    "context",
                    self._snapshot_locked(),
                    "max_context_tokens",
                )
            self._context_tokens += token_count
            return self._snapshot_locked()

    def remaining_for(self, tool: str) -> int:
        """Return the remaining calls for a tool, including the global limit."""

        normalized_tool = _normalize_identifier("tool", tool)
        with self._lock:
            if self._context_tokens >= self.max_context_tokens:
                return 0
            remaining = self.max_tool_calls - self._tool_calls
            if normalized_tool == self.DOCUMENT_SEARCH:
                remaining = min(
                    remaining,
                    self.max_document_search_calls - self._document_search_calls,
                )
            elif normalized_tool == self.WEB_SEARCH:
                remaining = min(
                    remaining,
                    self.max_web_search_calls - self._web_search_calls,
                )
            return max(remaining, 0)

    remaining_calls = remaining_for

    def _snapshot_locked(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            max_tool_calls=self.max_tool_calls,
            max_document_search_calls=self.max_document_search_calls,
            max_web_search_calls=self.max_web_search_calls,
            max_hits_per_tool=self.max_hits_per_tool,
            tool_timeout_seconds=self.tool_timeout_seconds,
            max_context_tokens=self.max_context_tokens,
            tool_calls=self._tool_calls,
            document_search_calls=self._document_search_calls,
            web_search_calls=self._web_search_calls,
            context_tokens=self._context_tokens,
            active_tool_calls=self._active_tool_calls,
            completed_tool_calls=self._completed_tool_calls,
            failed_tool_calls=self._failed_tool_calls,
            timed_out_tool_calls=self._timed_out_tool_calls,
            calls=tuple(self._calls),
        )

    def _reservation_reason_locked(self, tool: str) -> str | None:
        if self._tool_calls >= self.max_tool_calls:
            return "max_tool_calls"
        if self._context_tokens >= self.max_context_tokens:
            return "max_context_tokens"
        if tool == self.DOCUMENT_SEARCH and self._document_search_calls >= self.max_document_search_calls:
            return "max_document_search_calls"
        if tool == self.WEB_SEARCH and self._web_search_calls >= self.max_web_search_calls:
            return "max_web_search_calls"
        return None

    @staticmethod
    def _validate_limits(**limits: object) -> None:
        for field_name in (
            "max_tool_calls",
            "max_document_search_calls",
            "max_web_search_calls",
            "max_hits_per_tool",
            "max_context_tokens",
        ):
            _require_positive_int(field_name, limits[field_name])
        _require_finite_positive_float("tool_timeout_seconds", limits["tool_timeout_seconds"])


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
class WebSearchItem:
    """One normalized external search result."""

    title: str
    url: str
    snippet: str
    retrieved_at: str
    content: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _normalize_text("title", self.title))
        object.__setattr__(self, "url", _optional_url("url", self.url) or "")
        object.__setattr__(self, "snippet", _normalize_text("snippet", self.snippet))
        object.__setattr__(
            self,
            "retrieved_at",
            _normalize_text("retrieved_at", self.retrieved_at),
        )
        if not isinstance(self.content, str):
            raise ValueError("content must be a string")
        object.__setattr__(self, "content", self.content.strip())


@dataclass(frozen=True, slots=True)
class WebSearchResult:
    """Normalized result returned by the web-search port."""

    query: str
    items: tuple[WebSearchItem, ...] = ()
    status: str = "no_results"

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", _normalize_text("query", self.query))
        items = _require_tuple_of("items", self.items, WebSearchItem)
        urls = tuple(item.url for item in items)
        if len(set(urls)) != len(urls):
            raise ValueError("items must contain unique URLs")
        status = _normalize_identifier("status", self.status)
        object.__setattr__(self, "items", items)
        object.__setattr__(self, "status", status)

    @property
    def results(self) -> tuple[WebSearchItem, ...]:
        """Compatibility alias used by web-provider adapters."""

        return self.items


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
class SynthesisResult:
    """Validated structured output returned by an answer synthesizer."""

    answer: str
    used_evidence_ids: tuple[str, ...] = ()
    citations: tuple[Citation, ...] = ()
    image_evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        answer = _normalize_text("answer", self.answer)
        used_evidence_ids = _require_unique_identifier_tuple(
            "used_evidence_ids", self.used_evidence_ids
        )
        citations = _require_tuple_of("citations", self.citations, Citation)
        image_evidence_ids = _require_unique_identifier_tuple(
            "image_evidence_ids", self.image_evidence_ids
        )
        object.__setattr__(self, "answer", answer)
        object.__setattr__(self, "used_evidence_ids", used_evidence_ids)
        object.__setattr__(self, "citations", citations)
        object.__setattr__(self, "image_evidence_ids", image_evidence_ids)

    def validate_against(self, ledger: EvidenceLedger) -> None:
        """Reject output that cites evidence outside the immutable ledger."""

        if not isinstance(ledger, EvidenceLedger):
            raise ValueError("ledger must be an EvidenceLedger")
        evidence_by_id = {item.evidence_id: item for item in ledger.evidence}
        for evidence_id in self.used_evidence_ids:
            if evidence_id not in evidence_by_id:
                raise ValueError("used evidence must reference existing evidence")
        for citation in self.citations:
            if citation.evidence_id not in evidence_by_id:
                raise ValueError("citation must reference existing evidence")
        for evidence_id in self.image_evidence_ids:
            item = evidence_by_id.get(evidence_id)
            if item is None:
                raise ValueError("image evidence must reference existing evidence")
            if not item.image_refs:
                raise ValueError("image evidence must reference evidence with images")


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


def _require_finite_non_negative_float(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise ValueError(f"{name} must be a finite non-negative number")


def _require_finite_positive_float(name: str, value: object) -> None:
    _require_finite_non_negative_float(name, value)
    if float(value) <= 0:
        raise ValueError(f"{name} must be a finite positive number")


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
