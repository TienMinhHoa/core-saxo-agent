from __future__ import annotations

import json
import asyncio

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from saxophone.agent.contracts import AgentOutcome, AgentQuestion, Citation, RunBudget, SynthesisResult, WebSearchItem, WebSearchResult
from saxophone.agent.graph import AgentGraphDependencies
from saxophone.agent.orchestrator import MainAgent


class _Model(BaseChatModel):
    calls: int = 0
    tools_seen: list[str] = []
    invalid_selection: bool = False
    search_tool: str = "search_web"

    @property
    def _llm_type(self):
        return "scripted-react"

    def bind_tools(self, tools, **kwargs):
        self.tools_seen = [item.name for item in tools]
        return self

    def _generate(self, *args, **kwargs):
        raise AssertionError("async only")

    async def _agenerate(self, messages, **kwargs):
        self.calls += 1
        observations = [m for m in messages if isinstance(m, ToolMessage)]
        if not observations:
            name, args = self.search_tool, {"query": "145 chord progression"}
        elif len(observations) == 1:
            evidence_id = json.loads(observations[0].content)["candidates"][0]["evidence_id"]
            name, args = "select_context", {"evidence_ids": ["invented" if self.invalid_selection else evidence_id]}
        else:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Context selection complete."))])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{
            "name": name, "args": args, "id": f"call-{self.calls}", "type": "tool_call",
        }]))])


class _Docs:
    async def search(self, question, budget):
        raise AssertionError("explicit web request should not use docs")


class _Web:
    async def search(self, question, budget):
        from saxophone.agent.policies import run_with_budget
        async def search():
            return WebSearchResult(question.question, (WebSearchItem(
                "Chords", "https://example.test/chords", "I IV V", "2026-10-02",
            ), WebSearchItem("Unrelated", "https://example.test/other", "Unrelated evidence", "2026-10-02")), "ready")
        return await run_with_budget(budget, RunBudget.WEB_SEARCH, search)


class _Synthesis:
    def __init__(self):
        self.ledgers = []

    async def synthesize(self, ledger, *, config=None):
        self.ledgers.append(ledger)
        if not ledger.evidence:
            return SynthesisResult("No evidence found.")
        evidence_id = ledger.evidence[0].evidence_id
        return SynthesisResult("I IV V [1].", (evidence_id,), (Citation(evidence_id, "[1]"),))


@pytest.mark.anyio
async def test_main_uses_create_agent_tools_then_pipeline_synthesizes_selected_contexts():
    model, synthesis = _Model(), _Synthesis()
    agent = MainAgent(dependencies=AgentGraphDependencies(
        document_search=_Docs(), web_search=_Web(), synthesizer=synthesis,
        orchestrator_model=model,
    ))

    result = await agent.run("Tra web cong thuc 145", run_id="react-web")

    assert result.outcome is AgentOutcome.ANSWERED
    assert set(model.tools_seen) == {"search_docs", "search_web", "select_context"}
    assert "synthesize" not in model.tools_seen
    assert model.calls == 3
    assert len(synthesis.ledgers) == 1
    assert len(synthesis.ledgers[0].evidence) == 1
    assert result.state["selected_contexts"] == synthesis.ledgers[0].evidence
    assert synthesis.ledgers[0].evidence[0].url == "https://example.test/chords"


@pytest.mark.anyio
async def test_invalid_context_id_never_reaches_synthesis():
    model, synthesis = _Model(invalid_selection=True), _Synthesis()
    agent = MainAgent(dependencies=AgentGraphDependencies(
        document_search=_Docs(), web_search=_Web(), synthesizer=synthesis,
        orchestrator_model=model,
    ))

    result = await agent.run("Search web", run_id="react-invalid")

    assert result.outcome is AgentOutcome.FAILED
    assert synthesis.ledgers == []


@pytest.mark.anyio
async def test_old_total_tool_limit_does_not_block_context_selection():
    synthesis = _Synthesis()
    agent = MainAgent(dependencies=AgentGraphDependencies(
        document_search=_Docs(), web_search=_Web(), synthesizer=synthesis,
        orchestrator_model=_Model(),
    ))

    result = await agent.run("Search web", run_id="react-budget", budget=RunBudget(max_tool_calls=1))

    assert result.outcome is AgentOutcome.ANSWERED
    assert len(synthesis.ledgers) == 1
    assert synthesis.ledgers[0].budget_exhausted is False
    assert result.budget.snapshot().web_search_calls == 1
    assert result.budget.snapshot().tool_calls == 2


@pytest.mark.anyio
async def test_thinking_model_adapter_runs_the_library_tool_loop():
    from saxophone.platform.langchain_model import ThinkingToolChatModel

    class Provider:
        calls = []

        async def generate_structured(self, **kwargs):
            self.calls.append(kwargs)
            payload = json.loads(kwargs["user_prompt"])
            observations = [item for item in payload["conversation"] if item["role"] == "tool"]
            if not observations:
                output = {"action": "tool", "tool_name": "search_web", "arguments": {"query": "145 chord progression"}}
            elif len(observations) == 1:
                ref = json.loads(observations[0]["content"])["candidates"][0]["evidence_id"]
                output = {"action": "tool", "tool_name": "select_context", "arguments": {"evidence_ids": [ref]}}
            else:
                output = {"action": "finish"}
            return kwargs["response_model"].model_validate(output)

    provider, synthesis = Provider(), _Synthesis()
    agent = MainAgent(dependencies=AgentGraphDependencies(
        document_search=_Docs(), web_search=_Web(), synthesizer=synthesis,
        orchestrator_model=ThinkingToolChatModel(provider=provider),
    ))

    result = await agent.run("Search web", run_id="thinking-library")

    assert result.outcome is AgentOutcome.ANSWERED
    assert len(provider.calls) == 3
    assert all(call["task_type"] == "orchestrator_decision" for call in provider.calls)
    assert len(synthesis.ledgers[0].evidence) == 1


@pytest.mark.anyio
async def test_run_context_is_not_shared_between_concurrent_runs():
    class Model(_Model):
        async def _agenerate(self, messages, **kwargs):
            question = next(message.content for message in messages if message.type == "human")
            if question == "No search needed":
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Done"))])
            return await super()._agenerate(messages, **kwargs)

    synthesis = _Synthesis()
    agent = MainAgent(dependencies=AgentGraphDependencies(
        document_search=_Docs(), web_search=_Web(), synthesizer=synthesis,
        orchestrator_model=Model(),
    ))
    answered, empty = await asyncio.gather(
        agent.run("Search web", run_id="isolated-web"),
        agent.run("No search needed", run_id="isolated-empty"),
    )
    assert len(answered.state["selected_contexts"]) == 1
    assert empty.state["selected_contexts"] == ()
    assert empty.outcome is AgentOutcome.INSUFFICIENT_EVIDENCE


@pytest.mark.anyio
async def test_search_docs_child_returns_candidates_for_explicit_context_selection():
    from saxophone.agent.document_search import DocumentSearchResult
    from saxophone.agent.evidence_selection import SelectionResult
    from saxophone.agent.contracts import SelectionStrategy
    from saxophone.retrieval.models import ChunkHit
    from saxophone.retrieval.renderers import AnswerContextModel, SourceParagraph

    paragraph = SourceParagraph("p1", "music.md", "Chords", (), "I IV V", (), ("1",), (), "c1")

    class Docs:
        async def search(self, question, budget):
            return DocumentSearchResult(question.question, (ChunkHit("music.md", "c1", 1, "v1", {}),), (paragraph,))

    class Selector:
        async def select(self, request):
            return SelectionResult(SelectionStrategy.PARAGRAPH_DIRECT, AnswerContextModel((), (paragraph,), ("p1",)))

    synthesis = _Synthesis()
    agent = MainAgent(dependencies=AgentGraphDependencies(
        document_search=Docs(), paragraph_selector=Selector(), synthesizer=synthesis,
        orchestrator_model=_Model(search_tool="search_docs"),
    ))
    result = await agent.run("Explain 145", run_id="react-docs")
    assert result.outcome is AgentOutcome.ANSWERED
    assert result.ledger.evidence[0].paragraph == "p1"
