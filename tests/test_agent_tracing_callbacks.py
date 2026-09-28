from __future__ import annotations

from uuid import UUID

import pytest

from saxophone.agent.contracts import AgentOutcome, AgentQuestion
from saxophone.agent.document_search import DocumentSearchResult, DocumentSearchStatus
from saxophone.agent.langchain_callbacks import AgentTracingCallbackHandler
from saxophone.agent.orchestrator import MainAgent
from saxophone.agent.tracing import InMemoryTracer, ObservationKind, TraceStatus


@pytest.mark.anyio
async def test_tracing_callback_records_redacted_parent_child_lifecycle() -> None:
    tracer = InMemoryTracer(secrets=("private-key",))
    root = tracer.start_trace(run_id="run-callback", input={"api_key": "private-key"})
    callback = AgentTracingCallbackHandler(
        run_id="run-callback",
        tracer=tracer,
        root=root,
    )
    callback_id = UUID("00000000-0000-0000-0000-000000000011")

    await callback.on_tool_start(
        {"name": "document_search"},
        "private-key query",
        run_id=callback_id,
        inputs={"question": "safe"},
    )
    await callback.on_tool_end(
        {"answer": "safe", "authorization": "private-key"},
        run_id=callback_id,
    )
    callback.finish()
    root.end()

    records = tracer.records
    assert [record.kind for record in records] == [
        ObservationKind.TRACE,
        ObservationKind.TOOL,
    ]
    assert records[1].context.parent_observation_id == records[0].context.observation_id
    assert records[1].output == {
        "answer": "safe",
        "authorization": "[REDACTED]",
    }
    assert records[1].status is TraceStatus.OK


@pytest.mark.anyio
async def test_tracing_callback_closes_failed_generation_without_raw_error() -> None:
    tracer = InMemoryTracer()
    root = tracer.start_trace(run_id="run-generation")
    callback = AgentTracingCallbackHandler(
        run_id="run-generation",
        tracer=tracer,
        root=root,
    )
    callback_id = UUID("00000000-0000-0000-0000-000000000012")

    await callback.on_llm_start(
        {"name": "answer_model"},
        ["private prompt"],
        run_id=callback_id,
        tags=["synthesis"],
    )
    await callback.on_llm_error(
        RuntimeError("authorization=secret-value"),
        run_id=callback_id,
    )
    callback.finish()
    root.end()

    record = tracer.records[-1]
    assert record.kind is ObservationKind.GENERATION
    assert record.status is TraceStatus.ERROR
    assert record.error_code == "RuntimeError"
    assert "secret-value" not in repr(record)


@pytest.mark.anyio
async def test_main_agent_wraps_graph_invocation_in_shared_trace() -> None:
    tracer = InMemoryTracer()

    class Search:
        async def search(self, question: AgentQuestion, budget: object) -> DocumentSearchResult:
            return DocumentSearchResult(question.question, status=DocumentSearchStatus.NO_HITS)

    agent = MainAgent(document_search=Search(), tracer=tracer)

    result = await agent.run("What is a major triad?", run_id="run-main")

    assert result.outcome is AgentOutcome.INSUFFICIENT_EVIDENCE
    records = tracer.records
    assert records[0].kind is ObservationKind.TRACE
    assert records[0].context.run_id == "run-main"
    assert records[0].status is TraceStatus.OK
    assert any(record.context.parent_observation_id == records[0].context.observation_id for record in records[1:])
