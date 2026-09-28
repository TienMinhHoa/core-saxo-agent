"""Shared policies for enforcing the agent run budget.

The policy layer owns admission, timeout, and result limiting.  Graph nodes and
tool adapters can use it without knowing how the mutable budget stores counts.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic
from typing import Awaitable, Callable, Generic, Sequence, TypeVar

from .contracts import (
    AgentQuestion,
    BudgetExhaustedError,
    BudgetSnapshot,
    ClarificationCandidate,
    ClarificationRequest,
    RunBudget,
)


T = TypeVar("T")


class BudgetTimeoutError(TimeoutError):
    """Raised when a tool does not finish within the shared timeout."""

    def __init__(self, tool: str, timeout_seconds: float) -> None:
        self.tool = tool
        self.timeout_seconds = timeout_seconds
        super().__init__(f"tool {tool} exceeded {timeout_seconds:g}s timeout")


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    """Admission decision returned before a tool call consumes budget."""

    tool: str
    allowed: bool
    reason: str | None
    snapshot: BudgetSnapshot


class BudgetPolicy(Generic[T]):
    """Apply the same limits to every tool call in a run."""

    def __init__(self, budget: RunBudget) -> None:
        if not isinstance(budget, RunBudget):
            raise TypeError("budget must be a RunBudget")
        self.budget = budget

    def check(self, tool: str) -> BudgetDecision:
        """Inspect admission without consuming a reservation."""

        try:
            normalized_tool = _normalize_tool(tool)
        except ValueError as error:
            raise ValueError(str(error)) from error
        if self.budget.can_reserve(normalized_tool):
            return BudgetDecision(
                normalized_tool,
                True,
                None,
                self.budget.snapshot(),
            )
        snapshot = self.budget.snapshot()
        reason = _reason_for_snapshot(normalized_tool, snapshot)
        return BudgetDecision(normalized_tool, False, reason, snapshot)

    def require(self, tool: str) -> BudgetSnapshot:
        """Consume one call reservation or raise ``BudgetExhaustedError``."""

        return self.budget.reserve(_normalize_tool(tool))

    def limit_hits(self, hits: Sequence[T], *, tool: str | None = None) -> tuple[T, ...]:
        """Apply the run's result cap without mutating the supplied sequence."""

        if isinstance(hits, (str, bytes)) or not isinstance(hits, Sequence):
            raise TypeError("hits must be a sequence")
        if tool is not None:
            _normalize_tool(tool)
        return tuple(hits[: self.budget.max_hits_per_tool])

    def record_context_tokens(self, token_count: int) -> BudgetSnapshot:
        """Consume context-token capacity from the same shared run budget."""

        return self.budget.record_context_tokens(token_count)

    async def run(
        self,
        tool: str,
        operation: Callable[[], Awaitable[T]] | Awaitable[T],
        *,
        timeout_seconds: float | None = None,
    ) -> T:
        """Run one operation after admission and enforce the shared timeout."""

        return await run_with_budget(
            self.budget,
            tool,
            operation,
            timeout_seconds=timeout_seconds,
        )


class ClarificationPolicy:
    """Ask for a choice only when local evidence has competing meanings.

    Candidate interpretations are supplied by the search/decision adapter in
    ``clarification_candidates`` (with ``interpretations`` accepted as a
    compatibility alias).  The policy deliberately returns ``None`` for an
    empty or non-ready document result so a configured web-search fallback can
    run before asking the user.
    """

    def __init__(
        self,
        *,
        min_confidence: float = 0.6,
        max_confidence_gap: float = 0.12,
        max_options: int = 4,
        reason_code: str = "multiple_supported_interpretations",
        question_builder: Callable[[str, tuple[str, ...]], str] | None = None,
    ) -> None:
        self._min_confidence = _confidence_value(
            "min_confidence", min_confidence
        )
        self._max_confidence_gap = _confidence_value(
            "max_confidence_gap", max_confidence_gap
        )
        if (
            isinstance(max_options, bool)
            or not isinstance(max_options, int)
            or max_options < 2
        ):
            raise ValueError("max_options must be an integer at least 2")
        if not isinstance(reason_code, str) or not reason_code.strip():
            raise ValueError("reason_code must not be blank")
        if question_builder is not None and not callable(question_builder):
            raise TypeError("question_builder must be callable")
        self._max_options = max_options
        self._reason_code = reason_code.strip()
        self._question_builder = question_builder

    def __call__(self, state: object) -> ClarificationRequest | None:
        """Evaluate a graph state after document search has completed."""

        values = _state_values(state)
        result = values.get("document_result")
        if result is None or _status_value(result) != "ready":
            return None

        raw_candidates = values.get("clarification_candidates")
        if raw_candidates is None:
            raw_candidates = values.get("interpretation_candidates")
        if raw_candidates is None:
            raw_candidates = values.get("interpretations")
        if raw_candidates is None:
            raw_candidates = getattr(result, "clarification_candidates", None)
        if raw_candidates is None:
            raw_candidates = getattr(result, "interpretations", None)

        candidates = _coerce_clarification_candidates(raw_candidates)
        supported = [
            candidate
            for candidate in candidates
            if candidate.confidence >= self._min_confidence
        ]
        supported.sort(key=lambda candidate: (-candidate.confidence, candidate.label))
        if len(supported) < 2:
            return None
        if (
            supported[0].confidence - supported[1].confidence
            > self._max_confidence_gap
        ):
            return None

        options: list[str] = []
        for candidate in supported[: self._max_options]:
            if candidate.label not in options:
                options.append(candidate.label)
        if len(options) < 2:
            return None

        question = _question_text(values.get("question"))
        custom_question = values.get("clarification_question")
        if isinstance(custom_question, str) and custom_question.strip():
            question = custom_question.strip()
        if self._question_builder is not None:
            question = self._question_builder(question, tuple(options))
        return ClarificationRequest(question, tuple(options), self._reason_code)

    evaluate = __call__


def check_budget(budget: RunBudget, tool: str) -> BudgetDecision:
    """Return an admission decision without consuming a tool call."""

    return BudgetPolicy(budget).check(tool)


async def run_with_budget(
    budget: RunBudget,
    tool: str,
    operation: Callable[[], Awaitable[T]] | Awaitable[T],
    *,
    timeout_seconds: float | None = None,
) -> T:
    """Admit, execute, and close one budgeted async tool call.

    ``operation`` should normally be a zero-argument callable so an exhausted
    budget can reject the call before a coroutine is created.  A pre-created
    awaitable is accepted for adapter convenience and is closed on rejection
    when possible.
    """

    if not isinstance(budget, RunBudget):
        raise TypeError("budget must be a RunBudget")
    normalized_tool = _normalize_tool(tool)
    effective_timeout = _effective_timeout(budget, timeout_seconds)
    try:
        budget.reserve(normalized_tool)
    except BudgetExhaustedError:
        _close_unawaited(operation)
        raise

    started = monotonic()
    try:
        awaitable = operation() if callable(operation) else operation
        result = await asyncio.wait_for(awaitable, timeout=effective_timeout)
    except asyncio.TimeoutError as error:
        duration = monotonic() - started
        budget.timeout(normalized_tool, duration_seconds=duration)
        raise BudgetTimeoutError(normalized_tool, effective_timeout) from error
    except BaseException:
        budget.fail(normalized_tool, duration_seconds=monotonic() - started)
        raise
    else:
        budget.complete(
            normalized_tool,
            status="completed",
            duration_seconds=monotonic() - started,
        )
        return result


# Explicit aliases make the helper discoverable from adapters written during
# the migration while keeping one implementation of admission and timeout.
execute_with_budget = run_with_budget
enforce_budget = run_with_budget
call_with_budget = run_with_budget


def _normalize_tool(tool: object) -> str:
    if not isinstance(tool, str) or not tool.strip():
        raise ValueError("tool must be a non-empty string")
    normalized = tool.strip()
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized):
        raise ValueError("tool must not contain control characters")
    return normalized


def _reason_for_snapshot(tool: str, snapshot: BudgetSnapshot) -> str:
    if snapshot.remaining_tool_calls <= 0:
        return "max_tool_calls"
    if snapshot.remaining_context_tokens <= 0:
        return "max_context_tokens"
    if tool == RunBudget.DOCUMENT_SEARCH and snapshot.remaining_document_search_calls <= 0:
        return "max_document_search_calls"
    if tool == RunBudget.WEB_SEARCH and snapshot.remaining_web_search_calls <= 0:
        return "max_web_search_calls"
    return "budget_exhausted"


def _effective_timeout(budget: RunBudget, timeout_seconds: float | None) -> float:
    if timeout_seconds is None:
        return budget.tool_timeout_seconds
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not timeout_seconds > 0
    ):
        raise ValueError("timeout_seconds must be positive")
    if not math.isfinite(float(timeout_seconds)):
        raise ValueError("timeout_seconds must be finite")
    return min(float(timeout_seconds), budget.tool_timeout_seconds)


def _close_unawaited(operation: object) -> None:
    close = getattr(operation, "close", None)
    if callable(close):
        close()


def _confidence_value(name: str, value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0 <= value <= 1
    ):
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    return float(value)


def _state_values(state: object) -> Mapping[str, object]:
    if isinstance(state, Mapping):
        return state
    values: dict[str, object] = {}
    for name in (
        "question",
        "document_result",
        "clarification_candidates",
        "interpretation_candidates",
        "interpretations",
        "clarification_question",
    ):
        if hasattr(state, name):
            values[name] = getattr(state, name)
    return values


def _status_value(result: object) -> object:
    status = getattr(result, "status", None)
    return getattr(status, "value", status)


def _coerce_clarification_candidates(value: object) -> tuple[ClarificationCandidate, ...]:
    if value is None or isinstance(value, (str, bytes)):
        return ()
    if isinstance(value, Mapping):
        if any(key in value for key in ("label", "option", "name")):
            values = (value,)
        else:
            values = tuple(value.items())
    elif isinstance(value, Sequence):
        values = value
    else:
        return ()

    candidates: list[ClarificationCandidate] = []
    for item in values:
        candidate = _coerce_clarification_candidate(item)
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _coerce_clarification_candidate(value: object) -> ClarificationCandidate | None:
    if isinstance(value, ClarificationCandidate):
        return value
    if isinstance(value, Mapping):
        label = value.get("label", value.get("option", value.get("name")))
        confidence = value.get("confidence", 1.0)
        evidence_ids = value.get("evidence_ids", ())
        try:
            return ClarificationCandidate(label, confidence, tuple(evidence_ids))
        except (TypeError, ValueError):
            return None
    if isinstance(value, tuple) and len(value) == 2:
        try:
            return ClarificationCandidate(value[0], value[1])
        except (TypeError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        return ClarificationCandidate(value, 1.0)
    return None


def _question_text(value: object) -> str:
    if isinstance(value, AgentQuestion):
        return value.question
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "Which interpretation do you mean?"
