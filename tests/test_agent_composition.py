from __future__ import annotations

from dataclasses import dataclass, field, replace

import pytest
from fastapi.testclient import TestClient

from saxophone.agent.contracts import AgentOutcome, AgentQuestion, RunBudget
from saxophone.agent.document_search import DocumentSearchResult, DocumentSearchStatus
from saxophone.agent.graph import AgentGraphDependencies
from saxophone.agent.orchestrator import AgentRunResult
from saxophone.agent.streaming import AgentRunManager
from saxophone.agent.state import AgentStage
from saxophone.agent.tracing import InMemoryTracer
from saxophone.app.factory import (
    AppOverrides,
    _compose_agent_services,
    create_app,
)
from saxophone.app.settings import AppSettings


class _RemoteGpu:
    async def health(self):
        raise AssertionError("composition test must not call provider health")


class _ModelClient:
    async def invoke(self, request):
        raise AssertionError("composition test must not call the model")


class _NoHitDocumentSearch:
    async def search(self, question, budget):
        return DocumentSearchResult(
            query=question.question,
            status=DocumentSearchStatus.NO_HITS,
        )


@dataclass
class _Runner:
    calls: list[tuple[AgentQuestion, str]] = field(default_factory=list)

    async def run(self, question, *, run_id, callbacks=None):
        self.calls.append((question, run_id))
        return AgentRunResult(
            run_id=run_id,
            outcome=AgentOutcome.INSUFFICIENT_EVIDENCE,
            stage=AgentStage.COMPLETED,
            budget=RunBudget(),
        )


def _settings(tmp_path) -> AppSettings:
    return AppSettings.from_environment(
        {
            "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
            "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
            "SAXO_DATA_ROOT": str(tmp_path),
        }
    )


def test_composition_injects_agent_runner_and_owns_stream_manager(tmp_path) -> None:
    runner = _Runner()
    app = create_app(
        _settings(tmp_path),
        overrides=AppOverrides(
            remote_gpu_gateway=_RemoteGpu(),
            model_client=_ModelClient(),
            disable_vector_index=True,
            agent_runner=runner,
        ),
    )

    container = app.state.container
    assert container.agent_runner is runner
    assert isinstance(container.agent_run_manager, AgentRunManager)

    response = TestClient(app).post(
        "/agent/chat/stream",
        json={"question": "What is rhythm?"},
    )

    assert response.status_code == 200
    assert response.headers["x-agent-run-id"]
    assert [line for line in response.text.splitlines() if line.startswith("event:")] == [
        "event: run_started",
        "event: run_completed",
    ]
    assert runner.calls[0][0] == AgentQuestion("What is rhythm?", context_limit=4000)


def test_agent_composition_helper_preserves_explicit_runtime_overrides(tmp_path) -> None:
    runner = _Runner()
    manager = AgentRunManager()
    tracer = InMemoryTracer()

    composition = _compose_agent_services(
        _settings(tmp_path),
        AppOverrides(
            agent_runner=runner,
            agent_run_manager=manager,
            tracer=tracer,
        ),
    )

    assert composition.runner is runner
    assert composition.run_manager is manager
    assert composition.tracer is tracer


def test_composition_accepts_a_prebuilt_run_manager_without_replacing_it(tmp_path) -> None:
    runner = _Runner()
    manager = AgentRunManager()
    app = create_app(
        _settings(tmp_path),
        overrides=AppOverrides(
            remote_gpu_gateway=_RemoteGpu(),
            model_client=_ModelClient(),
            disable_vector_index=True,
            agent_runner=runner,
            agent_run_manager=manager,
        ),
    )

    assert app.state.container.agent_runner is runner
    assert app.state.container.agent_run_manager is manager


@pytest.mark.anyio
async def test_composition_compiles_injected_graph_and_uses_configured_run_budgets(
    tmp_path,
) -> None:
    settings = replace(
        _settings(tmp_path),
        agent_max_tool_calls=2,
        agent_max_document_search_calls=1,
        agent_max_web_search_calls=1,
        agent_max_hits_per_tool=3,
        agent_tool_timeout_seconds=4,
        agent_max_context_tokens=140,
    )
    app = create_app(
        settings,
        overrides=AppOverrides(
            remote_gpu_gateway=_RemoteGpu(),
            model_client=_ModelClient(),
            disable_vector_index=True,
            agent_graph_dependencies=AgentGraphDependencies(
                document_search=_NoHitDocumentSearch(),
            ),
        ),
    )

    container = app.state.container
    assert container.agent_runner is not None
    assert container.agent_runner.graph is not None
    assert isinstance(container.agent_run_manager, AgentRunManager)

    first = await container.agent_runner.run("question", run_id="configured-budget-1")
    second = await container.agent_runner.run("question", run_id="configured-budget-2")

    assert first.budget.snapshot().max_tool_calls == 2
    assert first.budget.snapshot().max_document_search_calls == 1
    assert first.budget.snapshot().max_web_search_calls == 1
    assert first.budget.snapshot().max_hits_per_tool == 3
    assert first.budget.snapshot().tool_timeout_seconds == 4
    assert first.budget.snapshot().max_context_tokens == 140
    assert first.budget is not second.budget
