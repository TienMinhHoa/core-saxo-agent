from __future__ import annotations

import asyncio

import pytest

from saxophone.agent.contracts import AgentQuestion, EvidenceLedger
from saxophone.agent.ports import (
    AgentTool,
    AnswerSynthesizer,
    DocumentSearchTool,
    EvidenceSelector,
    WebSearchTool,
    require_agent_tool,
)


class _FakeTool:
    name = "document_search"

    async def run(self, request: object, budget: object) -> object:
        return request, budget


class _FakeDocumentSearch:
    async def search(self, question: AgentQuestion, budget: object) -> object:
        return question, budget


class _FakeWebSearch:
    async def search(self, question: AgentQuestion, budget: object) -> object:
        return question, budget


class _FakeSelector:
    async def select(self, request: object) -> object:
        return request


class _FakeSynthesizer:
    async def synthesize(self, ledger: EvidenceLedger) -> object:
        return ledger


def test_agent_tool_contract_supports_async_injection() -> None:
    tool = _FakeTool()
    question = AgentQuestion("What is harmony?")

    assert isinstance(tool, AgentTool)
    validated = require_agent_tool(tool)
    result = asyncio.run(validated.run(question, object()))

    assert result[0] is question


def test_specialized_ports_are_structural_async_contracts() -> None:
    assert isinstance(_FakeDocumentSearch(), DocumentSearchTool)
    assert isinstance(_FakeWebSearch(), WebSearchTool)
    assert isinstance(_FakeSelector(), EvidenceSelector)
    assert isinstance(_FakeSynthesizer(), AnswerSynthesizer)


@pytest.mark.parametrize(
    "tool",
    [
        object(),
        type("MissingName", (), {"run": lambda self, request, budget: None})(),
        type("SyncRun", (), {"name": "sync", "run": lambda self, request, budget: None})(),
        type("BlankName", (), {"name": " ", "run": _FakeTool.run})(),
    ],
)
def test_require_agent_tool_rejects_invalid_contracts(tool: object) -> None:
    with pytest.raises(TypeError):
        require_agent_tool(tool)


def test_protocol_methods_are_not_accidentally_synchronous() -> None:
    assert asyncio.iscoroutinefunction(_FakeTool.run)
    assert asyncio.iscoroutinefunction(_FakeDocumentSearch.search)
    assert asyncio.iscoroutinefunction(_FakeWebSearch.search)
    assert asyncio.iscoroutinefunction(_FakeSelector.select)
    assert asyncio.iscoroutinefunction(_FakeSynthesizer.synthesize)
