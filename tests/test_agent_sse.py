from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from saxophone.agent.contracts import AgentOutcome
from saxophone.agent.events import AgentEvent, AgentEventType
from saxophone.agent.streaming import AgentRunManager
from saxophone.interfaces.agent_stream import encode_agent_event
from saxophone.interfaces.api import build_agent_chat_router


@dataclass
class _Runner:
    calls: list[tuple[object, str]] = field(default_factory=list)

    async def run(self, question: object, *, run_id: str, callbacks: object) -> object:
        self.calls.append((question, run_id))
        callback = callbacks[0]
        callback_id = UUID("00000000-0000-0000-0000-000000000101")
        await callback.on_chain_start(
            None,
            {},
            run_id=callback_id,
            tags=["langgraph_node:document_search_tool"],
        )
        await callback.on_llm_start(
            None,
            ["private prompt"],
            run_id=callback_id,
            tags=["public_answer"],
        )
        await callback.on_llm_new_token(
            "safe answer delta",
            run_id=callback_id,
            tags=["public_answer"],
        )
        return SimpleNamespace(outcome=AgentOutcome.ANSWERED)


class _FailingRunner:
    async def run(self, question: object, *, run_id: str, callbacks: object) -> object:
        del question, run_id, callbacks
        raise RuntimeError("provider secret must stay private")


def _app(*, runner: object | None, manager: AgentRunManager) -> FastAPI:
    app = FastAPI()
    app.include_router(
        build_agent_chat_router(
            agent_runner=runner,
            agent_run_manager=manager,
        )
    )
    return app


def _frames(body: str) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    for block in body.strip().split("\n\n"):
        data_line = next(line for line in block.splitlines() if line.startswith("data: "))
        frames.append(json.loads(data_line.removeprefix("data: ")))
    return frames


def test_agent_event_is_encoded_as_safe_sse_frame() -> None:
    frame = encode_agent_event(
        AgentEvent(
            AgentEventType.TOOL_PROGRESS,
            run_id="run-sse",
            tool="document_search",
            call_id="call-1",
            completed=1,
            total=2,
        )
    )

    assert frame.startswith("id: 0\nevent: tool_progress\ndata: ")
    assert frame.endswith("\n\n")
    assert json.loads(frame.split("data: ", 1)[1].strip()) == {
        "type": "tool_progress",
        "run_id": "run-sse",
        "tool": "document_search",
        "call_id": "call-1",
        "completed": 1,
        "total": 2,
    }


def test_agent_stream_route_emits_ordered_safe_progress_events() -> None:
    manager = AgentRunManager()
    runner = _Runner()

    response = TestClient(_app(runner=runner, manager=manager)).post(
        "/agent/chat/stream",
        json={"question": "What is rhythm?", "max_tokens": 1200},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-agent-run-id"]
    frames = _frames(response.text)
    assert [frame["type"] for frame in frames] == [
        "run_started",
        "stage_started",
        "synthesis_started",
        "answer_delta",
        "run_completed",
    ]
    assert [frame["sequence"] for frame in frames] == [1, 2, 3, 4, 5]
    assert "private prompt" not in response.text
    assert runner.calls[0][0].question == "What is rhythm?"
    assert runner.calls[0][0].context_limit == 1200


def test_agent_stream_route_replays_from_last_event_id_without_duplicate_events() -> None:
    manager = AgentRunManager()

    async def seed() -> None:
        await manager.start("run-replay")
        await manager.publish(
            AgentEvent(
                AgentEventType.STAGE_STARTED,
                run_id="run-replay",
                stage="document_search",
            )
        )
        await manager.publish(
            AgentEvent(
                AgentEventType.RUN_COMPLETED,
                run_id="run-replay",
                status="answered",
            )
        )

    import asyncio

    asyncio.run(seed())
    response = TestClient(_app(runner=None, manager=manager)).post(
        "/agent/chat/stream",
        headers={"X-Agent-Run-ID": "run-replay", "Last-Event-ID": "1"},
        json={"question": "ignored on replay"},
    )

    assert response.status_code == 200
    frames = _frames(response.text)
    assert [frame["sequence"] for frame in frames] == [2, 3]
    assert [frame["type"] for frame in frames] == ["stage_started", "run_completed"]


def test_agent_stream_route_requires_runner_for_new_runs() -> None:
    response = TestClient(_app(runner=None, manager=AgentRunManager())).post(
        "/agent/chat/stream",
        json={"question": "What is rhythm?"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "agent streaming capability is not configured"}


def test_agent_stream_route_redacts_runner_failures_in_terminal_event() -> None:
    response = TestClient(_app(runner=_FailingRunner(), manager=AgentRunManager())).post(
        "/agent/chat/stream",
        json={"question": "What is rhythm?"},
    )

    assert response.status_code == 200
    frames = _frames(response.text)
    assert frames[-1]["type"] == "run_failed"
    assert frames[-1]["error_code"] == "RuntimeError"
    assert "provider secret" not in response.text


def test_agent_stream_route_rejects_non_string_filter_values_before_starting_run() -> None:
    manager = AgentRunManager()
    response = TestClient(_app(runner=_Runner(), manager=manager)).post(
        "/agent/chat/stream",
        json={"question": "What is rhythm?", "filters": {"page": 4}},
    )

    assert response.status_code == 422
    assert "string values" in response.json()["detail"]
