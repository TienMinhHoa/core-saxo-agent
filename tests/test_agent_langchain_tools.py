from __future__ import annotations

from dataclasses import dataclass

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tools import BaseTool

from saxophone.agent.contracts import AgentQuestion, RunBudget, WebSearchItem, WebSearchResult
from saxophone.agent.document_search import DocumentSearchResult, DocumentSearchStatus
from saxophone.agent.langchain_tools import (
    DocumentSearchLangChainTool,
    WebSearchLangChainTool,
    create_document_search_tool,
    create_web_search_tool,
)


@dataclass
class _DocumentSearch:
    calls: list[tuple[AgentQuestion, RunBudget]]

    async def search(self, question: AgentQuestion, budget: RunBudget) -> DocumentSearchResult:
        self.calls.append((question, budget))
        return DocumentSearchResult(query=question.question, status=DocumentSearchStatus.NO_HITS)


@dataclass
class _WebSearch:
    calls: list[tuple[AgentQuestion, RunBudget]]

    async def search(self, question: AgentQuestion, budget: RunBudget) -> WebSearchResult:
        self.calls.append((question, budget))
        return WebSearchResult(
            query=question.question,
            items=(
                WebSearchItem(
                    title="Major triad",
                    url="https://example.test/triad",
                    snippet="A root, third, and fifth.",
                    retrieved_at="2026-09-29T10:00:00+00:00",
                ),
            ),
            status="ready",
        )


class _CallbackRecorder(BaseCallbackHandler):
    def __init__(self) -> None:
        self.started: list[dict[str, object]] = []
        self.completed = 0

    def on_tool_start(self, serialized, input_str, **kwargs):  # type: ignore[no-untyped-def]
        self.started.append(dict(kwargs.get("inputs") or {}))

    def on_tool_end(self, output, **kwargs):  # type: ignore[no-untyped-def]
        self.completed += 1


@pytest.mark.anyio
async def test_document_search_wrapper_is_a_real_langchain_tool_and_keeps_typed_budget() -> None:
    adapter = _DocumentSearch([])
    tool = create_document_search_tool(adapter)
    budget = RunBudget()

    assert isinstance(tool, BaseTool)
    assert isinstance(tool, DocumentSearchLangChainTool)
    assert tool.name == "document_search"
    assert "budget" not in tool.args_schema.model_json_schema()["properties"]

    result = await tool.ainvoke(
        {
            "question": "  What is a major triad?  ",
            "filters": {"source": "music.md"},
            "context_limit": 800,
            "budget": budget,
        }
    )

    assert isinstance(result, DocumentSearchResult)
    assert result.query == "What is a major triad?"
    assert adapter.calls == [
        (AgentQuestion("What is a major triad?", {"source": "music.md"}, 800), budget)
    ]


@pytest.mark.anyio
async def test_web_search_wrapper_returns_typed_results_and_emits_tool_callbacks() -> None:
    adapter = _WebSearch([])
    tool = create_web_search_tool(adapter)
    recorder = _CallbackRecorder()
    budget = RunBudget()

    result = await tool.ainvoke(
        {"question": "What is a major triad?", "budget": budget},
        config={"callbacks": [recorder]},
    )

    assert isinstance(tool, WebSearchLangChainTool)
    assert isinstance(result, WebSearchResult)
    assert result.status == "ready"
    assert len(result.items) == 1
    assert recorder.started == [{"question": "What is a major triad?"}]
    assert recorder.completed == 1
    assert adapter.calls[0][1] is budget


@pytest.mark.anyio
async def test_langchain_tool_search_alias_accepts_domain_question_and_budget() -> None:
    adapter = _DocumentSearch([])
    tool = create_document_search_tool(adapter)
    budget = RunBudget()

    result = await tool.search(AgentQuestion("question"), budget)

    assert isinstance(result, DocumentSearchResult)
    assert adapter.calls[0][0] == AgentQuestion("question")


@pytest.mark.anyio
async def test_langchain_tool_requires_runtime_budget_and_rejects_unknown_fields() -> None:
    tool = create_document_search_tool(_DocumentSearch([]))

    with pytest.raises(TypeError, match="RunBudget"):
        await tool.ainvoke({"question": "question"})

    with pytest.raises(Exception):
        await tool.ainvoke(
            {"question": "question", "budget": RunBudget(), "unknown": "field"}
        )
