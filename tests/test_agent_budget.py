from __future__ import annotations

import asyncio

import pytest

from saxophone.agent.contracts import BudgetExhaustedError, RunBudget
from saxophone.agent.policies import BudgetPolicy, BudgetTimeoutError, run_with_budget
from saxophone.app.settings import AppSettings, SettingsValidationError


VALID_ENVIRONMENT = {
    "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
    "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
}


def test_run_budget_defaults_and_snapshot_expose_shared_limits() -> None:
    budget = RunBudget()

    snapshot = budget.snapshot()

    assert snapshot.max_tool_calls == 8
    assert snapshot.max_document_search_calls == 3
    assert snapshot.max_web_search_calls == 2
    assert snapshot.max_hits_per_tool == 20
    assert snapshot.tool_timeout_seconds == 20.0
    assert snapshot.max_context_tokens == 12_000
    assert snapshot.remaining_tool_calls == 8
    assert snapshot.remaining_document_search_calls == 3
    assert snapshot.remaining_web_search_calls == 2


def test_document_and_web_calls_share_global_budget_without_resetting() -> None:
    budget = RunBudget(
        max_tool_calls=3,
        max_document_search_calls=2,
        max_web_search_calls=2,
    )

    budget.reserve("document_search")
    budget.complete("document_search")
    budget.reserve("document_search")
    budget.complete("document_search")
    budget.reserve("web_search")

    snapshot = budget.snapshot()
    assert snapshot.tool_calls == 3
    assert snapshot.document_search_calls == 2
    assert snapshot.web_search_calls == 1
    assert snapshot.remaining_tool_calls == 0
    with pytest.raises(BudgetExhaustedError, match="max_tool_calls"):
        budget.reserve("web_search")


def test_budget_policy_rejects_exhausted_call_before_invoking_operation() -> None:
    budget = RunBudget(max_tool_calls=1)
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        return "done"

    assert asyncio.run(run_with_budget(budget, "document_search", operation)) == "done"
    with pytest.raises(BudgetExhaustedError):
        asyncio.run(run_with_budget(budget, "web_search", operation))
    assert calls == 1
    assert budget.snapshot().completed_tool_calls == 1


def test_timeout_is_recorded_and_reservation_remains_consumed() -> None:
    budget = RunBudget(max_tool_calls=2, tool_timeout_seconds=0.01)

    async def slow_operation() -> None:
        await asyncio.sleep(0.05)

    with pytest.raises(BudgetTimeoutError, match="document_search"):
        asyncio.run(run_with_budget(budget, "document_search", slow_operation))

    snapshot = budget.snapshot()
    assert snapshot.tool_calls == 1
    assert snapshot.timed_out_tool_calls == 1
    assert snapshot.failed_tool_calls == 1
    assert snapshot.active_tool_calls == 0
    assert budget.trace[0].status == "timeout"


def test_concurrent_reservations_are_atomic() -> None:
    budget = RunBudget(max_tool_calls=2, max_document_search_calls=2)
    started = 0
    release = asyncio.Event()

    async def operation() -> str:
        nonlocal started
        started += 1
        await release.wait()
        return "ok"

    async def run_all() -> list[object]:
        tasks = [
            asyncio.create_task(run_with_budget(budget, "document_search", operation))
            for _ in range(5)
        ]
        await asyncio.sleep(0)
        release.set()
        return await asyncio.gather(*tasks, return_exceptions=True)

    results = asyncio.run(run_all())
    assert started == 2
    assert sum(result == "ok" for result in results) == 2
    assert sum(isinstance(result, BudgetExhaustedError) for result in results) == 3
    assert budget.snapshot().tool_calls == 2


def test_policy_limits_hits_and_context_tokens() -> None:
    budget = RunBudget(max_hits_per_tool=2, max_context_tokens=5)
    policy = BudgetPolicy(budget)

    assert policy.limit_hits((1, 2, 3), tool="document_search") == (1, 2)
    policy.record_context_tokens(5)
    with pytest.raises(BudgetExhaustedError, match="max_context_tokens"):
        policy.record_context_tokens(1)
    with pytest.raises(BudgetExhaustedError, match="max_context_tokens"):
        budget.reserve("web_search")


def test_settings_expose_agent_budget_defaults_and_environment_overrides() -> None:
    defaults = AppSettings.from_environment(VALID_ENVIRONMENT)
    assert defaults.agent_max_tool_calls == 8
    assert defaults.agent_max_document_search_calls == 3
    assert defaults.agent_max_web_search_calls == 2
    assert defaults.agent_max_hits_per_tool == 20
    assert defaults.agent_tool_timeout_seconds == 20.0
    assert defaults.agent_max_context_tokens == 12_000

    configured = AppSettings.from_environment(
        {
            **VALID_ENVIRONMENT,
            "SAXO_AGENT_MAX_TOOL_CALLS": "4",
            "SAXO_AGENT_MAX_DOCUMENT_SEARCH_CALLS": "2",
            "SAXO_AGENT_MAX_WEB_SEARCH_CALLS": "1",
            "SAXO_AGENT_MAX_HITS_PER_TOOL": "7",
            "SAXO_AGENT_TOOL_TIMEOUT_SECONDS": "3.5",
            "SAXO_AGENT_MAX_CONTEXT_TOKENS": "800",
        }
    )
    assert RunBudget.from_settings(configured).snapshot().max_tool_calls == 4
    assert configured.agent_max_document_search_calls == 2
    assert configured.agent_max_web_search_calls == 1
    assert configured.agent_max_hits_per_tool == 7
    assert configured.agent_tool_timeout_seconds == 3.5
    assert configured.agent_max_context_tokens == 800


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("SAXO_AGENT_MAX_TOOL_CALLS", "0"),
        ("SAXO_AGENT_MAX_DOCUMENT_SEARCH_CALLS", "bad"),
        ("SAXO_AGENT_MAX_WEB_SEARCH_CALLS", "-1"),
        ("SAXO_AGENT_MAX_HITS_PER_TOOL", "0"),
        ("SAXO_AGENT_TOOL_TIMEOUT_SECONDS", "0"),
        ("SAXO_AGENT_MAX_CONTEXT_TOKENS", "nan"),
    ],
)
def test_settings_reject_invalid_agent_budget_values(variable: str, value: str) -> None:
    with pytest.raises(SettingsValidationError, match=variable):
        AppSettings.from_environment({**VALID_ENVIRONMENT, variable: value})
