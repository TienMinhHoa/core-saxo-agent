from __future__ import annotations

from uuid import UUID

import pytest
from langchain_core.runnables import RunnableLambda

from saxophone.agent.events import AgentEventType
from saxophone.agent.langchain_callbacks import AgentEventCallbackHandler
from saxophone.agent.streaming import AgentRunManager


@pytest.mark.anyio
async def test_callback_maps_graph_node_to_safe_stage_event() -> None:
    manager = AgentRunManager()
    await manager.start("run-callback")
    callback = AgentEventCallbackHandler(run_id="run-callback", sink=manager)

    await callback.on_chain_start(
        {"name": "StateGraph"},
        {},
        run_id=UUID("00000000-0000-0000-0000-000000000001"),
        tags=["langgraph_node:document_search_tool"],
    )

    events = await manager.history("run-callback")
    assert events[-2].type is AgentEventType.STAGE_STARTED
    assert events[-2].stage == "document_search"
    assert events[-1].type is AgentEventType.THINKING
    assert events[-1].text == "Đang tìm tài liệu liên quan"


@pytest.mark.anyio
async def test_callback_tolerates_langchain_runnables_without_serialized_metadata() -> None:
    manager = AgentRunManager()
    await manager.start("run-missing-serialized")
    callback = AgentEventCallbackHandler(run_id="run-missing-serialized", sink=manager)

    await callback.on_chain_start(
        None,  # type: ignore[arg-type]
        {},
        run_id=UUID("00000000-0000-0000-0000-000000000006"),
        tags=["langgraph_node:web_search_tool"],
    )

    events = await manager.history("run-missing-serialized")
    assert events[-2].type is AgentEventType.STAGE_STARTED
    assert events[-2].stage == "web_search"
    assert events[-1].type is AgentEventType.THINKING
    assert events[-1].text == "Đang tìm thêm thông tin trên web"


@pytest.mark.anyio
async def test_callback_runs_through_langchain_async_runnable() -> None:
    manager = AgentRunManager()
    await manager.start("run-runnable")
    callback = AgentEventCallbackHandler(run_id="run-runnable", sink=manager)

    result = await RunnableLambda(lambda value: value + 1).ainvoke(
        1,
        config={
            "callbacks": [callback],
            "tags": ["langgraph_node:document_search_tool"],
        },
    )

    assert result == 2
    events = await manager.history("run-runnable")
    assert [event.type for event in events] == [
        AgentEventType.RUN_STARTED,
        AgentEventType.STAGE_STARTED,
        AgentEventType.THINKING,
    ]


@pytest.mark.anyio
async def test_callback_tracks_tool_lifecycle_without_streaming_input() -> None:
    manager = AgentRunManager()
    await manager.start("run-tool")
    callback = AgentEventCallbackHandler(run_id="run-tool", sink=manager)
    tool_run_id = UUID("00000000-0000-0000-0000-000000000002")

    await callback.on_tool_start(
        {"name": "document_search"},
        "private question text",
        run_id=tool_run_id,
    )
    await callback.on_tool_end(
        {"answer": "private result"},
        run_id=tool_run_id,
    )

    events = await manager.history("run-tool")
    assert [event.type for event in events[1:]] == [
        AgentEventType.TOOL_STARTED,
        AgentEventType.TOOL_COMPLETED,
    ]
    assert events[1].tool == "document_search"
    assert events[1].call_id == str(tool_run_id)
    assert events[1].text is None
    assert events[2].status == "completed"


@pytest.mark.anyio
async def test_callback_emits_only_opted_in_public_answer_deltas() -> None:
    manager = AgentRunManager()
    await manager.start("run-answer")
    callback = AgentEventCallbackHandler(run_id="run-answer", sink=manager)
    llm_run_id = UUID("00000000-0000-0000-0000-000000000003")

    await callback.on_llm_start(
        {"name": "answer_model"},
        ["private prompt"],
        run_id=llm_run_id,
        tags=["public_answer"],
    )
    await callback.on_llm_new_token(
        "hello",
        run_id=llm_run_id,
        tags=["public_answer"],
    )
    await callback.on_llm_start(
        {"name": "planning_model"},
        ["private prompt"],
        run_id=UUID("00000000-0000-0000-0000-000000000004"),
    )
    await callback.on_llm_new_token(
        "hidden",
        run_id=UUID("00000000-0000-0000-0000-000000000004"),
    )

    events = await manager.history("run-answer")
    assert [event.type for event in events[1:]] == [
        AgentEventType.SYNTHESIS_STARTED,
        AgentEventType.THINKING,
        AgentEventType.ANSWER_DELTA,
    ]
    assert events[-1].text == "hello"


@pytest.mark.anyio
async def test_callback_redacts_tool_error_to_error_code() -> None:
    manager = AgentRunManager()
    await manager.start("run-error")
    callback = AgentEventCallbackHandler(run_id="run-error", sink=manager)
    tool_run_id = UUID("00000000-0000-0000-0000-000000000005")

    await callback.on_tool_start(
        {"name": "web_search"},
        "secret query",
        run_id=tool_run_id,
    )
    await callback.on_tool_error(
        RuntimeError("authorization=secret-value"),
        run_id=tool_run_id,
    )

    event = (await manager.history("run-error"))[-1]
    assert event.type is AgentEventType.TOOL_COMPLETED
    assert event.status == "failed"
    assert event.error_code == "RuntimeError"
    assert "secret-value" not in str(event.as_dict())
