from __future__ import annotations

from dataclasses import replace
import json

import pytest
import tiktoken
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import Field

from saxophone.agent.contracts import (
    AgentOutcome, AgentQuestion, Citation, RunBudget, SynthesisResult, WebSearchItem, WebSearchResult,
)
from saxophone.agent.document_search import DocumentSearchResult
from saxophone.agent.evidence import EvidenceLedgerBuilder
from saxophone.agent.evidence_selection import SelectionResult
from saxophone.agent.graph import AgentGraphDependencies
from saxophone.agent.orchestrator import MainAgent
from saxophone.agent.policies import run_with_budget
from saxophone.agent.synthesis import EvidenceSynthesisService
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.renderers import AnswerContextModel, SourceParagraph


class _LoopModel(BaseChatModel):
    calls: int = 0
    search_tool: str = "search_web"
    select_after_search: bool = False
    observations: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "budget-ignoring-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, *args, **kwargs):
        raise AssertionError("Async only")

    async def _agenerate(self, messages, **kwargs):
        self.calls += 1
        observations = [message for message in messages if isinstance(message, ToolMessage)]
        self.observations = observations
        if self.select_after_search and len(observations) == 1:
            candidate = json.loads(observations[0].content)["candidates"][0]
            name, args = "select_context", {"evidence_ids": [candidate["evidence_id"]]}
        else:
            name, args = self.search_tool, {"query": "Alto saxophone transposition"}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{
            "name": name, "args": args, "id": f"budget-{self.calls}", "type": "tool_call",
        }]))])


class _Web:
    def __init__(self, *, empty=False, text="Alto is an E-flat instrument.", error=None):
        self.calls = 0
        self.empty = empty
        self.text = text
        self.error = error

    async def search(self, question, budget):
        async def search():
            self.calls += 1
            if self.error:
                raise self.error
            items = () if self.empty else (
                WebSearchItem("Alto", "https://example.test/alto", self.text, "2026-10-02"),
                WebSearchItem("More", "https://example.test/more", "Written C sounds E-flat.", "2026-10-02"),
            )
            return WebSearchResult(question.question, items, "no_hits" if self.empty else "ready")
        return await run_with_budget(budget, RunBudget.WEB_SEARCH, search)


class _Docs:
    def __init__(self):
        self.calls = 0
        self.paragraph = SourceParagraph(
            "p-alto", "music.md", "Transposition", (), "Alto is in E-flat.", (), ("42",), (), "c-alto",
        )

    async def search(self, question, budget):
        async def search():
            self.calls += 1
            return DocumentSearchResult(
                question.question, (ChunkHit("music.md", "c-alto", 1, "v1", {}),), (self.paragraph,),
            )
        return await run_with_budget(budget, RunBudget.DOCUMENT_SEARCH, search)


class _Selector:
    calls = 0

    async def select(self, request):
        self.calls += 1
        paragraphs = request.search_result.paragraph_candidates
        return SelectionResult("paragraph_direct", AnswerContextModel(
            (), paragraphs, tuple(item.paragraph_ref for item in paragraphs),
        ))


class _Synthesis:
    def __init__(self):
        self.ledgers = []

    async def synthesize(self, ledger, *, config=None):
        self.ledgers.append(ledger)
        if not ledger.evidence:
            return SynthesisResult("Using internal knowledge: alto is in E-flat.", evidence_sufficient=False)
        evidence_id = ledger.evidence[0].evidence_id
        return SynthesisResult("Alto is in E-flat [1].", (evidence_id,), (Citation(evidence_id, "[1]"),))


def _agent(model, synthesis, *, web=None, docs=None, selector=None):
    return MainAgent(dependencies=AgentGraphDependencies(
        document_search=docs or _Docs(), paragraph_selector=selector,
        web_search=web, synthesizer=synthesis, orchestrator_model=model,
    ))


@pytest.mark.anyio
async def test_exhausted_search_budget_still_synthesizes_existing_candidates():
    model, web, synthesis = _LoopModel(), _Web(), _Synthesis()
    budget = RunBudget(max_tool_calls=1, max_web_search_calls=1)
    result = await _agent(model, synthesis, web=web).run("Tra web saxophone alto", budget=budget)
    assert result.outcome is AgentOutcome.ANSWERED
    assert result.answer
    assert len(synthesis.ledgers) == 1
    ledger = synthesis.ledgers[0]
    assert ledger.budget_exhausted is True
    assert ledger.budget_reason == "max_web_search_calls"
    assert {item.url for item in ledger.evidence} == {"https://example.test/alto", "https://example.test/more"}
    assert budget.snapshot().tool_calls == 1
    assert web.calls == 1
    assert model.calls == 2, "Web-only scope allows one final selection turn after the web quota ends"


@pytest.mark.anyio
async def test_paragraph_selection_is_available_after_last_document_search():
    model = _LoopModel(search_tool="search_docs")
    docs, selector, synthesis = _Docs(), _Selector(), _Synthesis()
    result = await _agent(model, synthesis, docs=docs, selector=selector).run(
        "Explain alto transposition", budget=RunBudget(max_tool_calls=1, max_document_search_calls=1),
    )
    assert result.outcome is AgentOutcome.ANSWERED
    assert selector.calls == 1
    assert docs.calls == 1
    assert synthesis.ledgers[0].budget_exhausted is True
    assert synthesis.ledgers[0].evidence[0].paragraph == "p-alto"


@pytest.mark.anyio
async def test_previously_selected_contexts_are_preserved_when_budget_ends():
    model, synthesis = _LoopModel(select_after_search=True), _Synthesis()
    result = await _agent(model, synthesis, web=_Web()).run(
        "Tra web alto saxophone", budget=RunBudget(max_tool_calls=2, max_web_search_calls=1),
    )
    assert result.outcome is AgentOutcome.ANSWERED
    assert model.calls == 2
    assert len(synthesis.ledgers[0].evidence) == 1
    assert synthesis.ledgers[0].evidence[0].url == "https://example.test/alto"
    assert synthesis.ledgers[0].budget_exhausted is True


@pytest.mark.anyio
async def test_per_tool_limit_recovers_without_exceeding_it():
    model, web, synthesis = _LoopModel(), _Web(), _Synthesis()
    budget = RunBudget(max_tool_calls=8, max_web_search_calls=1)
    result = await _agent(model, synthesis, web=web).run("Tra web alto", budget=budget)
    assert result.outcome is AgentOutcome.ANSWERED
    assert web.calls == 1
    assert budget.snapshot().web_search_calls == 1
    assert synthesis.ledgers[0].budget_exhausted is True
    assert synthesis.ledgers[0].budget_reason == "max_web_search_calls"


@pytest.mark.anyio
async def test_no_candidates_at_budget_limit_can_return_internal_knowledge():
    synthesis = _Synthesis()
    result = await _agent(_LoopModel(), synthesis, web=_Web(empty=True)).run(
        "Tra web alto", budget=RunBudget(max_tool_calls=1),
    )
    assert result.outcome is AgentOutcome.ANSWERED
    assert result.answer
    assert result.synthesis.used_internal_knowledge is True
    assert synthesis.ledgers[0].evidence == ()
    assert result.synthesis.citations == ()


@pytest.mark.anyio
async def test_recovered_candidates_respect_context_token_limits():
    budget = RunBudget(max_tool_calls=1, max_context_tokens=32)
    synthesis = _Synthesis()
    result = await _agent(_LoopModel(), synthesis, web=_Web(text="alto " * 1000)).run(
        AgentQuestion("Tra web alto", context_limit=20), budget=budget,
    )
    assert result.outcome is AgentOutcome.ANSWERED
    ledger = synthesis.ledgers[0]
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = sum(len(encoding.encode(item.text, disallowed_special=())) for item in ledger.evidence)
    assert tokens <= 20
    assert budget.snapshot().context_tokens <= 32


@pytest.mark.anyio
async def test_unrelated_tool_errors_are_not_disguised_as_budget_exhaustion():
    synthesis = _Synthesis()
    result = await _agent(_LoopModel(), synthesis, web=_Web(error=RuntimeError("Web provider failed"))).run(
        "Tra web alto", budget=RunBudget(max_tool_calls=3),
    )
    assert result.outcome is AgentOutcome.FAILED
    assert synthesis.ledgers == []


class _StructuredModel:
    def __init__(self, output):
        self.output = output
        self.prompts = []

    def with_structured_output(self, schema):
        def invoke(prompt):
            self.prompts.append(prompt)
            return self.output
        return RunnableLambda(invoke)


def _ledger():
    builder = EvidenceLedgerBuilder("sufficiency", "Which key for alto?", "paragraph_direct")
    builder.add_web(title="Alto", url="https://example.test/alto", snippet="Alto is in E-flat.", retrieved_at="2026-10-02")
    return builder.build()


@pytest.mark.anyio
async def test_synthesis_receives_budget_status_and_returns_supported_answer_when_sufficient():
    ledger = replace(_ledger(), budget_exhausted=True, budget_reason="max_tool_calls")
    evidence_id = ledger.evidence[0].evidence_id
    model = _StructuredModel({
        "evidence_sufficient": True, "answer": "Alto is in E-flat [1].",
        "used_evidence_ids": [evidence_id], "citations": [{"evidence_id": evidence_id, "label": "[1]"}],
    })
    result = await EvidenceSynthesisService(model).synthesize(ledger)
    rendered = model.prompts[0].to_string().lower()
    assert "budget_exhausted" in rendered
    assert "max_tool_calls" in rendered
    assert "sufficien" in rendered
    assert result.evidence_sufficient is True
    assert result.used_internal_knowledge is False
    assert result.answer == "Alto is in E-flat [1]."


@pytest.mark.anyio
@pytest.mark.parametrize("with_context", [False, True])
async def test_insufficient_sources_produce_disclosed_internal_answer_without_fake_sources(with_context):
    ledger = _ledger() if with_context else EvidenceLedgerBuilder("empty", "Which key for alto?", "paragraph_direct").build()
    model = _StructuredModel({
        "evidence_sufficient": False, "answer": "For concert C major, write A major for alto saxophone.",
        "used_evidence_ids": [], "citations": [],
    })
    result = await EvidenceSynthesisService(model).synthesize(ledger)
    assert result.used_internal_knowledge is True
    assert result.evidence_sufficient is False
    assert "kiến thức nội tại" in result.answer
    assert "chưa tìm thấy" in result.answer.lower() or "không tìm thấy" in result.answer.lower()
    assert "write A major" in result.answer
    assert result.citations == ()
    assert result.used_evidence_ids == ()


@pytest.mark.anyio
async def test_internal_answer_cannot_claim_fabricated_citation():
    with pytest.raises(ValueError):
        await EvidenceSynthesisService(_StructuredModel({
            "evidence_sufficient": False, "answer": "Write A major [1].",
            "used_evidence_ids": [], "citations": [],
        })).synthesize(_ledger())


@pytest.mark.anyio
async def test_empty_ledger_cannot_be_declared_sufficient_for_a_grounded_answer():
    ledger = EvidenceLedgerBuilder("empty-grounded", "Which key for alto?", "paragraph_direct").build()
    with pytest.raises(ValueError):
        await EvidenceSynthesisService(_StructuredModel({
            "evidence_sufficient": True, "answer": "Write A major.",
            "used_evidence_ids": [], "citations": [],
        })).synthesize(ledger)
