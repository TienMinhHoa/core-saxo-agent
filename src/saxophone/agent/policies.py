"""Shared policies for enforcing the agent run budget.

The policy layer owns admission, timeout, and result limiting.  Graph nodes and
tool adapters can use it without knowing how the mutable budget stores counts.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from time import monotonic
from typing import Awaitable, Callable, Generic, Sequence, TypeVar

from .contracts import BudgetExhaustedError, BudgetSnapshot, RunBudget


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
