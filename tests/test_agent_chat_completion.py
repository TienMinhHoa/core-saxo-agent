from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from saxophone.agent.contracts import (
    AgentOutcome,
    Citation,
    ClarificationRequest,
    RunBudget,
    SynthesisResult,
)
from saxophone.agent.evidence import EvidenceLedgerBuilder
from saxophone.agent.events import AgentEventType
from saxophone.agent.langchain_callbacks import AgentEventCallbackHandler
from saxophone.agent.orchestrator import AgentRunResult
from saxophone.agent.state import AgentStage
from saxophone.agent.streaming import AgentRunManager
from saxophone.interfaces.api import build_agent_chat_router


@dataclass
class _Runner:
    result: AgentRunResult
    calls: int = 0

    async def run(self, question, *, run_id, callbacks):
        self.calls += 1
        return self.result


class _Gate:
    def __init__(self, rejected=()):
        self.rejected = set(rejected)
        self.calls = []

    async def validate(self, refs):
        self.calls.append(refs)
        if self.rejected.intersection(refs):
            raise ValueError("secret artifact storage details")
        return refs


def _answered(*, images=(), label="[1]") -> AgentRunResult:
    builder = EvidenceLedgerBuilder(
        run_id="run-answer", question="What is a triad?", selected_strategy="paragraph_direct"
    )
    cited = builder.add_document(
        source_ref="music.md", chunk_id="chunk-1", paragraph_ref="paragraph-1",
        text="A triad has three notes.", page=12, image_refs=images, score=0.73,
    )
    builder.add_document(
        source_ref="music.md", chunk_id="chunk-2", paragraph_ref="paragraph-2",
        text="Uncited text.", page=13, image_refs=("images/uncited.png",),
    )
    ledger = builder.build()
    synthesis = SynthesisResult(
        "A triad has three notes " + label + ".", (cited.evidence_id,),
        (Citation(cited.evidence_id, label),), (cited.evidence_id,) if images else (),
    )
    return AgentRunResult(
        "run-answer", AgentOutcome.ANSWERED, AgentStage.COMPLETED, RunBudget(),
        answer=synthesis.answer, ledger=ledger, synthesis=synthesis,
        state={"private_prompt": "DO NOT STREAM THIS"},
    )


def _app(runner, gate=None):
    app = FastAPI()
    app.include_router(build_agent_chat_router(
        agent_runner=runner, agent_run_manager=AgentRunManager(), image_artifact_gate=gate,
    ))
    return app


def _frames(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def _result_frame(frames):
    results = [frame for frame in frames if frame["type"] == "run_result"]
    assert len(results) == 1, "SSE must deliver one validated final result before completion"
    return results[0]["result"]


def test_non_streaming_model_still_delivers_answer_and_cited_sources_over_sse() -> None:
    runner = _Runner(_answered())
    response = TestClient(_app(runner)).post("/agent/chat/stream", json={"question": "Triads?"})
    frames = _frames(response)
    payload = _result_frame(frames)

    assert response.status_code == 200
    assert payload["status"] == "answered"
    assert payload["answer"] == runner.result.answer
    assert len(payload["sources"]) == 1
    assert payload["sources"][0]["paragraph_ref"] == "paragraph-1"
    assert payload["sources"][0]["page_start"] == 12
    assert payload["sources"][0]["image_refs"] == []
    assert payload["sources"][0]["score"] == 0.73
    assert [frame["type"] for frame in frames][-2:] == ["run_result", "run_completed"]
    assert "DO NOT STREAM THIS" not in response.text
    assert "ledger" not in payload


def test_sse_sources_preserve_synthesis_citation_labels() -> None:
    response = TestClient(_app(_Runner(_answered(label="[7]")))).post(
        "/agent/chat/stream", json={"question": "Triads?"}
    )
    payload = _result_frame(_frames(response))

    assert payload["sources"][0]["citation"] == "[7]"
    assert "[7]" in payload["answer"]


@pytest.mark.parametrize("rejected", [(), ("images/triad.png",)])
def test_sse_resolves_only_cited_images_and_suppresses_invalid_artifacts(rejected) -> None:
    gate = _Gate(rejected)
    response = TestClient(_app(_Runner(_answered(images=("images/triad.png",))), gate)).post(
        "/agent/chat/stream", json={"question": "Triads?"}
    )
    source = _result_frame(_frames(response))["sources"][0]

    assert gate.calls == [("images/triad.png",)]
    assert "images/uncited.png" not in response.text
    assert "secret artifact storage details" not in response.text
    if rejected:
        assert not source.get("images")
        assert source["image_errors"]
    else:
        assert source["images"][0]["url"] == "/api/v1/assets/images/triad.png"


def test_sse_delivers_clarification_question_options_and_run_identity() -> None:
    runner = _Runner(AgentRunResult(
        "run-choice", AgentOutcome.NEEDS_CLARIFICATION, AgentStage.WAITING_FOR_CLARIFICATION,
        RunBudget(), clarification=ClarificationRequest(
            "Which triad?", ("Major triad", "Minor triad"), "multiple_supported_interpretations"
        ),
    ))
    response = TestClient(_app(runner)).post("/agent/chat/stream", json={"question": "Triads?"})
    frames = _frames(response)
    payload = _result_frame(frames)

    assert payload["status"] == "needs_clarification"
    assert payload["clarification"]["options"] == ["Major triad", "Minor triad"]
    assert payload["answer"] is None
    assert frames[-1]["run_id"] == response.headers["x-agent-run-id"]


@pytest.mark.parametrize("outcome", [AgentOutcome.INSUFFICIENT_EVIDENCE, AgentOutcome.BUDGET_EXHAUSTED])
def test_sse_delivers_structured_outcome_even_without_answer(outcome) -> None:
    runner = _Runner(AgentRunResult("run-empty", outcome, AgentStage.COMPLETED, RunBudget(), state={"reason_code": outcome.value}))
    response = TestClient(_app(runner)).post("/agent/chat/stream", json={"question": "Triads?"})
    payload = _result_frame(_frames(response))

    assert payload["status"] == outcome.value
    assert payload["answer"] is None
    assert payload["sources"] == []


def test_final_result_is_replayable_without_running_model_again() -> None:
    runner = _Runner(_answered())
    client = TestClient(_app(runner))
    first = client.post("/agent/chat/stream", json={"question": "Triads?"})
    frames = _frames(first)
    result = next(frame for frame in frames if frame["type"] == "run_result")
    replay = client.post(
        "/agent/chat/stream", json={"question": "ignored"}, headers={
            "X-Agent-Run-ID": first.headers["x-agent-run-id"],
            "Last-Event-ID": str(result["sequence"] - 1),
        },
    )

    assert _result_frame(_frames(replay)) == result["result"]
    assert runner.calls == 1


@pytest.mark.anyio
async def test_tool_completion_events_include_counts_and_confidence_without_raw_text() -> None:
    events = []

    class Sink:
        async def publish(self, event):
            events.append(event)

    callback = AgentEventCallbackHandler(run_id="run-progress", sink=Sink())
    tool_id = uuid4()
    await callback.on_tool_start({"name": "document_search"}, "private query", run_id=tool_id)
    await callback.on_tool_end(
        SimpleNamespace(hits=(object(), object()), confidence=0.85), run_id=tool_id
    )
    payload = next(
        event.as_dict() for event in events if event.type is AgentEventType.TOOL_COMPLETED
    )

    assert payload["hit_count"] == 2
    assert payload["confidence"] == 0.85
    assert "private query" not in json.dumps([event.as_dict() for event in events])
