from __future__ import annotations

from uuid import UUID

import pytest

from saxophone.agent.events import AgentEvent, AgentEventType
from saxophone.agent.langchain_callbacks import AgentEventCallbackHandler
from saxophone.agent.streaming import AgentRunManager


def test_thinking_event_serializes_a_safe_one_line_progress_summary() -> None:
    event = AgentEvent(
        AgentEventType.THINKING,
        run_id="run-thinking",
        text="Đã tìm thấy 3 chunk",
    )

    assert event.as_dict() == {
        "type": "thinking",
        "run_id": "run-thinking",
        "text": "Đã tìm thấy 3 chunk",
    }


@pytest.mark.parametrize("text", [None, "", "   ", "đang tìm\nprivate prompt"])
def test_thinking_event_rejects_missing_or_multiline_text(text: str | None) -> None:
    with pytest.raises(ValueError, match="thinking text"):
        AgentEvent(AgentEventType.THINKING, run_id="run-thinking", text=text)


@pytest.mark.anyio
async def test_callback_emits_allowlisted_thinking_for_document_search() -> None:
    manager = AgentRunManager()
    await manager.start("run-thinking-stage")
    callback = AgentEventCallbackHandler(run_id="run-thinking-stage", sink=manager)

    await callback.on_chain_start(
        None,
        {},
        run_id=UUID("00000000-0000-0000-0000-000000000201"),
        tags=["langgraph_node:document_search_tool"],
    )

    events = await manager.history("run-thinking-stage")
    thinking = [event for event in events if event.type is AgentEventType.THINKING]
    assert [event.text for event in thinking] == ["Đang tìm tài liệu liên quan"]


@pytest.mark.anyio
async def test_callback_emits_counted_thinking_without_private_tool_output() -> None:
    manager = AgentRunManager()
    await manager.start("run-thinking-tool")
    callback = AgentEventCallbackHandler(run_id="run-thinking-tool", sink=manager)
    tool_run_id = UUID("00000000-0000-0000-0000-000000000202")

    await callback.on_tool_start(
        {"name": "document_search"},
        "private query text",
        run_id=tool_run_id,
    )
    await callback.on_tool_end(
        {"hits": [{"secret": "private"}, {"secret": "private"}]},
        run_id=tool_run_id,
    )

    events = await manager.history("run-thinking-tool")
    thinking = [event for event in events if event.type is AgentEventType.THINKING]
    assert [event.text for event in thinking] == ["Đã tìm thấy 2 chunk"]
    assert "private" not in str([event.as_dict() for event in thinking])


@pytest.mark.anyio
async def test_callback_maps_selection_decision_to_safe_thinking_summary() -> None:
    manager = AgentRunManager()
    await manager.start("run-thinking-decision")
    callback = AgentEventCallbackHandler(run_id="run-thinking-decision", sink=manager)

    await callback.on_chain_end(
        {
            "decision": "select",
            "reason_code": "local_evidence_available",
            "thinking": "private chain of thought",
        },
        run_id=UUID("00000000-0000-0000-0000-000000000203"),
    )

    events = await manager.history("run-thinking-decision")
    thinking = [event for event in events if event.type is AgentEventType.THINKING]
    assert [event.text for event in thinking] == ["Đang chọn paragraph liên quan"]
    assert "private chain of thought" not in str([event.as_dict() for event in thinking])

