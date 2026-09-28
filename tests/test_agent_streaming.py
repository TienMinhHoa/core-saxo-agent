from __future__ import annotations

import pytest

from saxophone.agent.events import AgentEvent, AgentEventType
from saxophone.agent.streaming import AgentRunManager


def test_agent_event_serializes_only_allowlisted_progress_fields() -> None:
    event = AgentEvent(
        AgentEventType.TOOL_PROGRESS,
        run_id="run-1",
        tool="document_search",
        call_id="call-1",
        completed=2,
        total=3,
    )

    assert event.as_dict() == {
        "type": "tool_progress",
        "run_id": "run-1",
        "tool": "document_search",
        "call_id": "call-1",
        "completed": 2,
        "total": 3,
    }


def test_agent_event_rejects_missing_required_fields() -> None:
    with pytest.raises(ValueError, match="stage is required"):
        AgentEvent(AgentEventType.STAGE_STARTED, run_id="run-1")
    with pytest.raises(ValueError, match="call_id is required"):
        AgentEvent(
            AgentEventType.TOOL_STARTED,
            run_id="run-1",
            tool="document_search",
        )
    with pytest.raises(ValueError, match="completed must not exceed total"):
        AgentEvent(
            AgentEventType.TOOL_PROGRESS,
            run_id="run-1",
            tool="document_search",
            call_id="call-1",
            completed=4,
            total=3,
        )


@pytest.mark.anyio
async def test_run_manager_orders_events_and_replays_after_sequence() -> None:
    manager = AgentRunManager()
    await manager.start("run-1")
    await manager.publish(
        AgentEvent(
            AgentEventType.STAGE_STARTED,
            run_id="run-1",
            stage="understanding",
        )
    )
    await manager.publish(
        AgentEvent(
            AgentEventType.RUN_COMPLETED,
            run_id="run-1",
            status="answered",
        )
    )

    events = [event async for event in manager.events("run-1")]
    assert [event.type for event in events] == [
        AgentEventType.RUN_STARTED,
        AgentEventType.STAGE_STARTED,
        AgentEventType.RUN_COMPLETED,
    ]
    assert [event.sequence for event in events] == [1, 2, 3]

    replay = [event async for event in manager.events("run-1", after_sequence=1)]
    assert [event.sequence for event in replay] == [2, 3]


@pytest.mark.anyio
async def test_run_manager_streams_live_events_to_subscribers() -> None:
    manager = AgentRunManager()
    await manager.start("run-live")
    stream = manager.events("run-live")

    first = await anext(stream)
    assert first.type is AgentEventType.RUN_STARTED

    await manager.publish(
        AgentEvent(
            AgentEventType.ANSWER_DELTA,
            run_id="run-live",
            text="hello",
        )
    )
    second = await anext(stream)
    assert second.type is AgentEventType.ANSWER_DELTA
    assert second.text == "hello"

    await manager.publish(
        AgentEvent(
            AgentEventType.RUN_COMPLETED,
            run_id="run-live",
            status="answered",
        )
    )
    terminal = await anext(stream)
    assert terminal.type is AgentEventType.RUN_COMPLETED
    with pytest.raises(StopAsyncIteration):
        await anext(stream)


@pytest.mark.anyio
async def test_run_manager_cancels_active_run_with_safe_failure_event() -> None:
    manager = AgentRunManager()
    await manager.start("run-cancel")

    assert await manager.cancel("run-cancel") is True
    events = [event async for event in manager.events("run-cancel")]

    assert events[-1].type is AgentEventType.RUN_FAILED
    assert events[-1].error_code == "client_disconnected"
    assert await manager.cancel("run-cancel") is False


@pytest.mark.anyio
async def test_run_manager_rejects_unknown_or_terminal_publish() -> None:
    manager = AgentRunManager()
    with pytest.raises(KeyError, match="unknown run"):
        await manager.publish(
            AgentEvent(AgentEventType.RUN_STARTED, run_id="missing")
        )

    await manager.start("run-terminal")
    await manager.publish(
        AgentEvent(
            AgentEventType.RUN_COMPLETED,
            run_id="run-terminal",
            status="answered",
        )
    )
    with pytest.raises(ValueError, match="already reached a terminal state"):
        await manager.publish(
            AgentEvent(
                AgentEventType.STAGE_STARTED,
                run_id="run-terminal",
                stage="synthesis",
            )
        )


@pytest.mark.anyio
async def test_run_manager_finishes_replay_after_terminal_sequence() -> None:
    manager = AgentRunManager()
    await manager.start("run-replay-complete")
    await manager.publish(
        AgentEvent(
            AgentEventType.RUN_COMPLETED,
            run_id="run-replay-complete",
            status="answered",
        )
    )

    events = [
        event
        async for event in manager.events("run-replay-complete", after_sequence=2)
    ]

    assert events == []
