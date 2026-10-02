from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from saxophone.agent.contracts import (
    AgentOutcome, Citation, SelectionStrategy, SynthesisResult, WebSearchItem, WebSearchResult,
)
from saxophone.agent.document_search import DocumentSearchResult
from saxophone.agent.evidence_selection import SelectionResult
from saxophone.agent.orchestrator import MainAgent
from saxophone.agent.streaming import AgentRunManager
from saxophone.interfaces.api import build_agent_chat_router
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.renderers import AnswerContextModel, SourceParagraph


def _events(caplog: pytest.LogCaptureFixture) -> list[dict]:
    return [record.chat_event for record in caplog.records if hasattr(record, "chat_event")]


def _callback(run_id: str):
    from saxophone.agent.logging import AgentLoggingCallbackHandler

    return AgentLoggingCallbackHandler(run_id=run_id, logger=logging.getLogger("saxophone.chat"))


class _Search:
    def __init__(self, *, empty: bool = False, error: bool = False):
        self.empty = empty
        self.error = error

    async def search(self, question, budget):
        if self.error:
            raise RuntimeError("authorization=provider-secret")
        if self.empty:
            return DocumentSearchResult(question.question)
        return DocumentSearchResult(
            question.question,
            hits=(ChunkHit("music.md", "chunk-1", 1, "v1", {}, semantic_score=0.9),),
            paragraph_candidates=(SourceParagraph(
                "paragraph-1", "music.md", "Triads", (),
                "A triad has three notes.", (), ("12",), (), "chunk-1",
            ),),
            confidence=0.9,
        )


class _Selector:
    async def select(self, request):
        paragraph = request.search_result.paragraph_candidates[0]
        return SelectionResult(
            SelectionStrategy.PARAGRAPH_DIRECT,
            AnswerContextModel((), (paragraph,), (paragraph.paragraph_ref,)),
        )


class _Synthesizer:
    def __init__(self, *, invalid_citation=False):
        self.invalid_citation = invalid_citation

    async def synthesize(self, ledger, *, config=None):
        evidence_id = "unknown-evidence" if self.invalid_citation else ledger.evidence[0].evidence_id
        return SynthesisResult(
            "A triad has three notes [1].", (evidence_id,), (Citation(evidence_id, "[1]"),),
        )


def _agent(**search_options):
    return MainAgent(
        document_search=_Search(**search_options),
        paragraph_selector=_Selector(),
        synthesizer=_Synthesizer(),
    )


@pytest.mark.anyio
async def test_agent_logs_results_of_every_graph_step_without_sse_or_langfuse(caplog):
    caplog.set_level(logging.INFO, logger="saxophone.chat")

    result = await _agent().run("What is a triad?", run_id="run-log-happy")

    assert result.outcome is AgentOutcome.ANSWERED
    events = _events(caplog)
    assert events[0]["event"] == "agent.run.started"
    assert events[-1]["event"] == "agent.run.completed"
    assert all(event["run_id"] == "run-log-happy" for event in events)
    completed = {
        event["node"]: event for event in events if event["event"] == "agent.step.completed"
    }
    assert set(completed) >= {
        "receive_question", "document_search_tool", "evaluate_local_evidence",
        "choose_selection_strategy", "select_evidence", "synthesize", "validate_answer", "completed",
    }
    search = completed["document_search_tool"]
    assert search["hit_count"] == 1
    assert search["chunk_ids"] == ["chunk-1"]
    assert search["paragraph_count"] == 1
    assert search["confidence"] == 0.9
    assert completed["select_evidence"]["selected_paragraph_refs"] == ["paragraph-1"]
    assert completed["choose_selection_strategy"]["selection_strategy"] == "paragraph_direct"
    assert completed["synthesize"]["citation_count"] == 1
    assert completed["synthesize"]["answer_chars"] == len(result.answer)
    assert completed["validate_answer"]["outcome"] == "answered"
    assert all(event["duration_ms"] >= 0 for event in completed.values())


@pytest.mark.anyio
async def test_no_hits_logs_zero_counts_and_reason_for_not_answering(caplog):
    caplog.set_level(logging.INFO, logger="saxophone.chat")

    result = await _agent(empty=True).run("Unknown topic", run_id="run-log-empty")

    assert result.outcome is AgentOutcome.INSUFFICIENT_EVIDENCE
    events = _events(caplog)
    search = next(event for event in events if event.get("node") == "document_search_tool"
                  and event["event"] == "agent.step.completed")
    assert search["hit_count"] == 0
    assert search["search_status"] == "no_hits"
    assert events[-1]["outcome"] == "insufficient_evidence"
    assert not any(event.get("node") == "synthesize" for event in events)


@pytest.mark.anyio
async def test_handled_tool_failure_is_logged_as_error_with_failed_node(caplog):
    caplog.set_level(logging.INFO, logger="saxophone.chat")

    result = await _agent(error=True).run("Triads?", run_id="run-log-error")

    assert result.outcome is AgentOutcome.FAILED
    failures = [event for event in _events(caplog) if event["event"] == "agent.step.failed"]
    assert any(event["node"] == "document_search_tool" for event in failures)
    assert _events(caplog)[-1]["event"] == "agent.run.failed"
    assert any(record.levelno >= logging.ERROR for record in caplog.records)
    assert "provider-secret" not in caplog.text


@pytest.mark.anyio
async def test_invalid_citation_is_logged_at_validation_and_final_answer_is_rejected(caplog):
    caplog.set_level(logging.INFO, logger="saxophone.chat")
    agent = MainAgent(
        document_search=_Search(), paragraph_selector=_Selector(),
        synthesizer=_Synthesizer(invalid_citation=True),
    )

    result = await agent.run("Triads?", run_id="run-log-citation")

    assert result.outcome is AgentOutcome.FAILED
    assert result.answer is None
    assert any(event["event"] == "agent.step.failed" and event["node"] == "validate_answer"
               for event in _events(caplog))


@pytest.mark.anyio
async def test_parallel_runs_keep_distinct_ids_and_each_has_one_final_log(caplog):
    caplog.set_level(logging.INFO, logger="saxophone.chat")
    agent = _agent()

    await asyncio.gather(
        agent.run("Triads?", run_id="run-log-a"),
        agent.run("Triads?", run_id="run-log-b"),
    )

    events = _events(caplog)
    for run_id in ("run-log-a", "run-log-b"):
        own = [event for event in events if event["run_id"] == run_id]
        assert sum(event["event"] == "agent.run.started" for event in own) == 1
        assert sum(event["event"] == "agent.run.completed" for event in own) == 1
        assert any(event.get("node") == "select_evidence" for event in own)


@pytest.mark.anyio
async def test_web_fallback_logs_result_count_and_source_urls(caplog):
    caplog.set_level(logging.INFO, logger="saxophone.chat")

    class WebSearch:
        async def search(self, question, budget):
            return WebSearchResult(question.question, (WebSearchItem(
                "Triads", "https://example.test/triads", "A triad has three notes.", "2026-10-01",
            ),), status="ready")

    agent = MainAgent(
        document_search=_Search(empty=True), web_search=WebSearch(), synthesizer=_Synthesizer(),
    )

    result = await agent.run("Triads?", run_id="run-log-web")

    assert result.outcome is AgentOutcome.ANSWERED
    web = next(event for event in _events(caplog) if event.get("node") == "web_search_tool"
               and event["event"] == "agent.step.completed")
    assert web["result_count"] == 1
    assert web["source_urls"] == ["https://example.test/triads"]


@pytest.mark.anyio
async def test_cancellation_logs_terminal_status_and_still_propagates(caplog):
    caplog.set_level(logging.INFO, logger="saxophone.chat")

    class CancelledGraph:
        async def ainvoke(self, state, *, config):
            raise asyncio.CancelledError()

    agent = MainAgent(graph=CancelledGraph())

    with pytest.raises(asyncio.CancelledError):
        await agent.run("Triads?", run_id="run-log-cancelled")

    assert _events(caplog)[-1]["event"] == "agent.run.cancelled"


@pytest.mark.anyio
async def test_step_logger_does_not_dump_arbitrary_state_prompts_or_reasoning(caplog):
    caplog.set_level(logging.DEBUG, logger="saxophone.chat")
    callback = _callback("run-log-private")
    node_id = uuid4()
    await callback.on_chain_start(
        None, {"api_key": "private-key", "prompt": "private prompt"},
        run_id=node_id, metadata={"langgraph_node": "document_search_tool"},
    )
    await callback.on_chain_end(
        {"document_result": DocumentSearchResult("Triads?"),
         "thinking": "private reasoning", "api_key": "private-key"}, run_id=node_id,
    )

    assert any(event["event"] == "agent.step.completed" for event in _events(caplog))
    assert all(value not in caplog.text for value in ("private-key", "private prompt", "private reasoning"))


@pytest.mark.anyio
async def test_debug_answer_preview_is_bounded_and_not_logged_at_info(caplog):
    callback = _callback("run-log-preview")
    caplog.set_level(logging.INFO, logger="saxophone.chat")
    node_id = uuid4()
    await callback.on_chain_start(None, {}, run_id=node_id, metadata={"langgraph_node": "synthesize"})
    await callback.on_chain_end({"answer": "a" * 2000}, run_id=node_id)
    assert not any("answer_preview" in event for event in _events(caplog))

    caplog.clear()
    caplog.set_level(logging.DEBUG, logger="saxophone.chat")
    node_id = uuid4()
    await callback.on_chain_start(None, {}, run_id=node_id, metadata={"langgraph_node": "synthesize"})
    await callback.on_chain_end({"answer": "a" * 2000}, run_id=node_id)
    previews = [event["answer_preview"] for event in _events(caplog) if "answer_preview" in event]
    assert previews and all(0 < len(value) <= 512 for value in previews)


def test_logging_configuration_writes_details_to_console_and_daily_file_without_duplicates():
    from saxophone.platform.chat_logging import configure_chat_logging

    root = Path("test-artifacts/chat-logging")
    root.mkdir(parents=True, exist_ok=True)
    console = io.StringIO()
    logger = logging.getLogger("saxophone.chat")
    original = (list(logger.handlers), logger.level, logger.propagate)
    try:
        configure_chat_logging(log_directory=root, stream=console, level="INFO")
        configure_chat_logging(log_directory=root, stream=console, level="INFO")
        marker = uuid4().hex
        logger.info("agent.step.completed", extra={"chat_event": {
            "event": "agent.step.completed", "run_id": marker,
            "node": "document_search_tool", "hit_count": 2, "duration_ms": 12.5,
        }})

        assert console.getvalue().count(marker) == 1
        assert "hit_count" in console.getvalue() and "duration_ms" in console.getvalue()
        content = "".join(path.read_text(encoding="utf-8") for path in root.glob("*.log"))
        assert content.count(marker) == 1
        assert "document_search_tool" in content
    finally:
        for handler in logger.handlers:
            if handler not in original[0]:
                handler.close()
        logger.handlers, logger.level, logger.propagate = original


def test_sse_route_logs_request_and_output_with_the_stream_run_id(caplog):
    caplog.set_level(logging.INFO, logger="saxophone.chat")
    app = FastAPI()
    app.include_router(build_agent_chat_router(agent_runner=_agent(), agent_run_manager=AgentRunManager()))

    response = TestClient(app).post("/agent/chat/stream", json={"question": "Triads?"})

    assert response.status_code == 200
    run_id = response.headers["x-agent-run-id"]
    events = [event for event in _events(caplog) if event["run_id"] == run_id]
    received = next(event for event in events if event["event"] == "chat.request.received")
    output = next(event for event in events if event["event"] == "chat.response.completed")
    assert received["route"] == "stream"
    assert output["status"] == "answered"
    assert output["source_count"] == 1
    assert output["answer_chars"] > 0


def test_legacy_json_route_also_logs_request_and_final_result(caplog):
    caplog.set_level(logging.INFO, logger="saxophone.chat")

    class Chat:
        async def answer(self, request):
            return SimpleNamespace(status="answered", answer="Three notes.", sources=())

    app = FastAPI()
    app.include_router(build_agent_chat_router(agent_chat=Chat()))

    response = TestClient(app).post("/agent/chat/messages", json={"question": "Triads?"})

    assert response.status_code == 200
    events = _events(caplog)
    received = next(event for event in events if event["event"] == "chat.request.received")
    output = next(event for event in events if event["event"] == "chat.response.completed")
    assert received["route"] == "json"
    assert received["run_id"] == output["run_id"]
    assert output["status"] == "answered"
    assert output["answer_chars"] == len("Three notes.")
