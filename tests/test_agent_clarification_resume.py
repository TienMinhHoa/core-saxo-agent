from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from saxophone.agent.contracts import (
    AgentOutcome, AgentQuestion, Citation, ClarificationRequest, RunBudget,
    SelectionStrategy, SynthesisResult,
)
from saxophone.agent.document_search import DocumentSearchResult, DocumentSearchStatus
from saxophone.agent.evidence_selection import SelectionResult
from saxophone.agent.orchestrator import AgentRunResult, MainAgent
from saxophone.agent.policies import run_with_budget
from saxophone.agent.state import AgentStage
from saxophone.agent.streaming import AgentRunManager
from saxophone.interfaces.api import build_agent_chat_router
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.renderers import AnswerContextModel, SourceParagraph


@dataclass
class _Search:
    calls: list = field(default_factory=list)

    async def search(self, question, budget):
        async def operation():
            self.calls.append((question, budget))
            return DocumentSearchResult(
                question.question,
                (ChunkHit("music.md", "chunk-1", 1, "v1", {"document_ref": "book"}, semantic_score=0.9),),
                (_paragraph(),), status=DocumentSearchStatus.READY,
            )
        return await run_with_budget(budget, "document_search", operation)


def _paragraph():
    return SourceParagraph(
        "paragraph-1", "music.md", "Major triad", (),
        "A major triad has a root, third, and fifth.", (), ("1",), (), "chunk-1",
    )


class _Selector:
    async def select(self, request):
        return SelectionResult(
            SelectionStrategy.PARAGRAPH_DIRECT,
            AnswerContextModel((), (_paragraph(),), ("paragraph-1",)),
        )


@dataclass
class _Synthesizer:
    calls: int = 0

    async def synthesize(self, ledger):
        self.calls += 1
        evidence_id = ledger.evidence[0].evidence_id
        return SynthesisResult(
            "A major triad has three notes [1].", (evidence_id,), (Citation(evidence_id, "[1]"),)
        )


def _choice_policy(state):
    if "Major triad" in state["question"].question or "Minor triad" in state["question"].question:
        return None
    return ClarificationRequest(
        "Which triad?", ("Major triad", "Minor triad"), "multiple_supported_interpretations"
    )


def _agent():
    search = _Search()
    synthesizer = _Synthesizer()
    agent = MainAgent(
        document_search=search, paragraph_selector=_Selector(),
        synthesizer=synthesizer, clarification_policy=_choice_policy,
    )
    return agent, search, synthesizer


@pytest.mark.anyio
async def test_clarification_resume_keeps_question_scope_run_id_and_shared_budget() -> None:
    agent, search, synthesizer = _agent()
    graph = agent.graph
    first = await agent.run(
        AgentQuestion("Which triad?", filters={"document_ref": "book"}, context_limit=200),
        run_id="run-choice",
    )
    assert first.outcome is AgentOutcome.NEEDS_CLARIFICATION
    assert synthesizer.calls == 0

    resumed = await agent.resume(run_id=first.run_id, option="Major triad")

    assert resumed.outcome is AgentOutcome.ANSWERED
    assert resumed.run_id == first.run_id
    assert resumed.budget is first.budget
    assert resumed.budget.snapshot().document_search_calls == 2
    assert agent.graph is graph
    assert len(search.calls) == 2
    assert "Which triad?" in search.calls[-1][0].question
    assert "Major triad" in search.calls[-1][0].question
    assert search.calls[-1][0].filters == {"document_ref": "book"}
    assert search.calls[-1][0].context_limit == 200
    assert resumed.clarification is None
    assert synthesizer.calls == 1


@pytest.mark.anyio
async def test_clarification_resume_preserves_chat_history() -> None:
    from saxophone.agent.contracts import ChatHistoryMessage

    agent, search, _ = _agent()
    history = (ChatHistoryMessage("assistant", "We are discussing alto saxophone."),)
    first = await agent.run(AgentQuestion("Which triad?", history=history), run_id="history-choice")
    assert first.outcome is AgentOutcome.NEEDS_CLARIFICATION

    resumed = await agent.resume(run_id=first.run_id, option="Major triad")

    assert resumed.outcome is AgentOutcome.ANSWERED
    assert search.calls[-1][0].history == history


@pytest.mark.anyio
@pytest.mark.parametrize("option", ["Unlisted interpretation", "", " "])
async def test_resume_rejects_invalid_choice_without_spending_budget(option) -> None:
    agent, search, synthesizer = _agent()
    first = await agent.run("Which triad?", run_id="run-invalid-choice")
    before = first.budget.snapshot()

    with pytest.raises(ValueError):
        await agent.resume(run_id=first.run_id, option=option)

    assert len(search.calls) == 1
    assert first.budget.snapshot() == before
    assert synthesizer.calls == 0


@pytest.mark.anyio
async def test_resume_cannot_reset_exhausted_budget() -> None:
    agent, search, synthesizer = _agent()
    first = await agent.run(
        "Which triad?", run_id="run-budget-choice",
        budget=RunBudget(max_document_search_calls=1),
    )

    resumed = await agent.resume(run_id=first.run_id, option="Major triad")

    assert resumed.outcome is AgentOutcome.BUDGET_EXHAUSTED
    assert resumed.budget is first.budget
    assert len(search.calls) == 1
    assert synthesizer.calls == 0


@pytest.mark.anyio
async def test_unknown_run_cannot_be_resumed() -> None:
    agent, search, synthesizer = _agent()

    with pytest.raises((KeyError, ValueError)):
        await agent.resume(run_id="unknown", option="Major triad")

    assert search.calls == []


@pytest.mark.anyio
async def test_answered_run_cannot_be_resumed_or_synthesized_twice() -> None:
    agent, search, synthesizer = _agent()
    await agent.run("What is a Major triad?", run_id="already-answered")

    with pytest.raises(ValueError):
        await agent.resume(run_id="already-answered", option="Major triad")

    assert len(search.calls) == 1
    assert synthesizer.calls == 1


def test_resume_http_route_continues_same_run_and_emits_only_new_events() -> None:
    agent, search, synthesizer = _agent()
    app = FastAPI()
    app.include_router(build_agent_chat_router(agent_runner=agent, agent_run_manager=AgentRunManager()))
    client = TestClient(app)
    first = client.post("/agent/chat/stream", json={"question": "Which triad?"})
    run_id = first.headers["x-agent-run-id"]
    first_frames = [json.loads(line[6:]) for line in first.text.splitlines() if line.startswith("data: ")]

    response = client.post(f"/agent/chat/runs/{run_id}/resume", json={"option": "Major triad"})

    assert response.status_code == 200
    assert response.headers["x-agent-run-id"] == run_id
    frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert frames[0]["sequence"] > first_frames[-1]["sequence"]
    assert frames[-1]["status"] == "answered"
    assert next(frame for frame in frames if frame["type"] == "run_result")["result"]["answer"]
    assert len(search.calls) == 2
    assert synthesizer.calls == 1


def test_resume_http_route_rejects_invalid_option_and_allows_valid_retry() -> None:
    agent, search, synthesizer = _agent()
    app = FastAPI()
    app.include_router(build_agent_chat_router(agent_runner=agent, agent_run_manager=AgentRunManager()))
    client = TestClient(app)
    first = client.post("/agent/chat/stream", json={"question": "Which triad?"})
    run_id = first.headers["x-agent-run-id"]

    invalid = client.post(f"/agent/chat/runs/{run_id}/resume", json={"option": "Unlisted"})
    assert invalid.status_code == 422
    assert len(search.calls) == 1

    valid = client.post(f"/agent/chat/runs/{run_id}/resume", json={"option": "Major triad"})
    assert valid.status_code == 200
    assert synthesizer.calls == 1
