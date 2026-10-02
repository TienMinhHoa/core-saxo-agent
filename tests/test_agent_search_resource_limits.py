"""Regression cases for independent search quotas and insufficient-doc fallback."""

from __future__ import annotations

import asyncio
import json

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from saxophone.agent.contracts import (
    AgentOutcome, BudgetExhaustedError, Citation, RunBudget, SynthesisResult,
    WebSearchItem, WebSearchResult,
)
from saxophone.agent.document_search import DocumentSearchResult
from saxophone.agent.evidence_selection import SelectionResult
from saxophone.agent.graph import AgentGraphDependencies
from saxophone.agent.orchestrator import MainAgent
from saxophone.agent.policies import run_with_budget
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.renderers import AnswerContextModel, SourceParagraph


def test_docs_three_and_web_two_are_independent_of_the_old_total_limit():
    budget = RunBudget(max_tool_calls=1, max_document_search_calls=3, max_web_search_calls=2)
    for name in [RunBudget.DOCUMENT_SEARCH] * 3 + [RunBudget.WEB_SEARCH] * 2:
        budget.reserve(name)
        budget.complete(name)
    snapshot = budget.snapshot()
    assert snapshot.document_search_calls == 3
    assert snapshot.web_search_calls == 2
    assert budget.remaining_for(RunBudget.DOCUMENT_SEARCH) == 0
    assert budget.remaining_for(RunBudget.WEB_SEARCH) == 0
    for name, reason in [(RunBudget.DOCUMENT_SEARCH, "max_document_search_calls"),
                         (RunBudget.WEB_SEARCH, "max_web_search_calls")]:
        with pytest.raises(BudgetExhaustedError) as failure:
            budget.reserve(name)
        assert failure.value.reason == reason


def test_selection_substeps_cannot_spend_the_remaining_web_quota():
    budget = RunBudget(max_tool_calls=1)
    for name in [RunBudget.DOCUMENT_SEARCH, "search_docs_selection", "select_context"] * 3:
        budget.reserve(name)
        budget.complete(name)
    assert budget.snapshot().document_search_calls == 3
    assert budget.remaining_for(RunBudget.WEB_SEARCH) == 2
    assert budget.can_reserve("select_context")


@pytest.mark.anyio
async def test_concurrent_search_admission_keeps_each_resource_within_its_quota():
    budget = RunBudget(max_tool_calls=1)

    async def attempt(name):
        try:
            await run_with_budget(budget, name, lambda: asyncio.sleep(0))
            return name
        except BudgetExhaustedError:
            return None

    admitted = await asyncio.gather(*[
        attempt(name) for name in [RunBudget.DOCUMENT_SEARCH] * 6 + [RunBudget.WEB_SEARCH] * 5
    ])
    assert admitted.count(RunBudget.DOCUMENT_SEARCH) == 3
    assert admitted.count(RunBudget.WEB_SEARCH) == 2


class _EarlyFinishModel(BaseChatModel):
    calls: int = 0

    @property
    def _llm_type(self):
        return "premature-docs-only-orchestrator"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, *args, **kwargs):
        raise AssertionError("Async only")

    async def _agenerate(self, messages, **kwargs):
        self.calls += 1
        observations = [item for item in messages if isinstance(item, ToolMessage)]
        if not observations:
            name, args = "search_docs", {"query": "công thức 145 là gì"}
        elif observations[-1].name in {"search_docs", "search_web"}:
            candidates = json.loads(observations[-1].content).get("candidates", [])
            name, args = "select_context", {"evidence_ids": [item["evidence_id"] for item in candidates]}
        else:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Finish with current context."))])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{
            "name": name, "args": args, "id": f"early-{self.calls}", "type": "tool_call",
        }]))])


class _Docs:
    def __init__(self, *, empty=False):
        self.empty = empty
        self.calls = 0
        self.paragraph = SourceParagraph(
            "p-table", "music-theory-full", "Table 14-2", (),
            "Common chord progressions include I, ii, iii, IV, V, vi, vii°.",
            (), ("222",), (), "c-table",
        )

    async def search(self, question, budget):
        async def perform():
            self.calls += 1
            if self.empty:
                return DocumentSearchResult(question.question)
            return DocumentSearchResult(question.question,
                                        (ChunkHit("music-theory-full", "c-table", 1, "v1", {}),),
                                        (self.paragraph,))
        return await run_with_budget(budget, RunBudget.DOCUMENT_SEARCH, perform)


class _QuotaIgnoringModel(_EarlyFinishModel):
    async def _agenerate(self, messages, **kwargs):
        self.calls += 1
        if self.calls <= 4:
            name, args = "search_docs", {"query": "145 chord formula"}
        elif self.calls <= 7:
            name, args = "search_web", {"query": "145 chord formula"}
        elif self.calls == 8:
            ids = []
            for message in messages:
                if isinstance(message, ToolMessage) and message.name == "search_web":
                    ids.extend(item["evidence_id"] for item in json.loads(message.content).get("candidates", []))
            name, args = "select_context", {"evidence_ids": list(dict.fromkeys(ids))}
        else:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Finish."))])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{
            "name": name, "args": args, "id": f"quota-{self.calls}", "type": "tool_call",
        }]))])


class _Selector:
    async def select(self, request):
        paragraphs = request.search_result.paragraph_candidates
        return SelectionResult("paragraph_direct", AnswerContextModel(
            (), paragraphs, tuple(item.paragraph_ref for item in paragraphs),
        ))


class _Web:
    def __init__(self, *, empty=False, error=None):
        self.empty = empty
        self.error = error
        self.calls = 0

    async def search(self, question, budget):
        async def perform():
            self.calls += 1
            if self.error:
                raise self.error
            items = () if self.empty else (WebSearchItem(
                "I IV V", "https://example.test/145", "145 means chords on scale degrees I, IV, V.", "2026-10-02",
            ),)
            return WebSearchResult(question.question, items, "no_hits" if self.empty else "ready")
        return await run_with_budget(budget, RunBudget.WEB_SEARCH, perform)


class _Synthesis:
    def __init__(self, *, docs_sufficient=False):
        self.docs_sufficient = docs_sufficient
        self.ledgers = []

    async def synthesize(self, ledger, *, config=None):
        self.ledgers.append(ledger)
        web = next((item for item in ledger.evidence if item.url), None)
        evidence = web or (ledger.evidence[0] if self.docs_sufficient and ledger.evidence else None)
        if evidence is None:
            return SynthesisResult(
                "Tạm thời chưa tìm thấy đủ thông tin; dùng kiến thức nội tại: 145 là I–IV–V.",
                evidence_sufficient=False,
            )
        return SynthesisResult("145 là I–IV–V [1].", (evidence.evidence_id,),
                               (Citation(evidence.evidence_id, "[1]"),), evidence_sufficient=True)


def _agent(docs, web, synthesis):
    return MainAgent(dependencies=AgentGraphDependencies(
        document_search=docs, paragraph_selector=_Selector(), web_search=web,
        synthesizer=synthesis, orchestrator_model=_EarlyFinishModel(),
    ))


@pytest.mark.anyio
@pytest.mark.parametrize("empty_docs", [False, True])
async def test_insufficient_internal_sources_force_web_even_when_main_finishes_early(empty_docs):
    docs, web, synthesis = _Docs(empty=empty_docs), _Web(), _Synthesis()
    budget = RunBudget(max_tool_calls=1)
    result = await _agent(docs, web, synthesis).run("công thức 145 là gì", budget=budget)
    assert result.outcome is AgentOutcome.ANSWERED
    assert 1 <= docs.calls <= 3
    assert 1 <= web.calls <= 2
    assert budget.snapshot().document_search_calls <= 3
    assert budget.snapshot().web_search_calls <= 2
    assert result.synthesis.evidence_sufficient is True
    assert result.synthesis.citations
    assert any(item.url == "https://example.test/145" for item in synthesis.ledgers[-1].evidence)


@pytest.mark.anyio
async def test_sufficient_documents_do_not_trigger_unnecessary_web_search():
    docs, web, synthesis = _Docs(), _Web(), _Synthesis(docs_sufficient=True)
    result = await _agent(docs, web, synthesis).run("công thức 145 là gì")
    assert result.outcome is AgentOutcome.ANSWERED
    assert docs.calls == 1
    assert web.calls == 0
    assert result.synthesis.evidence_sufficient is True


@pytest.mark.anyio
async def test_exceeding_docs_quota_leaves_web_available_and_cannot_exceed_either_quota():
    docs, web, synthesis = _Docs(), _Web(), _Synthesis()
    agent = MainAgent(dependencies=AgentGraphDependencies(
        document_search=docs, paragraph_selector=_Selector(), web_search=web,
        synthesizer=synthesis, orchestrator_model=_QuotaIgnoringModel(),
    ))
    result = await agent.run("công thức 145 là gì", budget=RunBudget(max_tool_calls=1))
    assert result.outcome is AgentOutcome.ANSWERED
    assert docs.calls == 3
    assert web.calls == 2
    assert result.synthesis.evidence_sufficient is True
    assert result.synthesis.citations


@pytest.mark.anyio
async def test_empty_web_fallback_ends_with_internal_answer_within_search_quotas():
    docs, web, synthesis = _Docs(), _Web(empty=True), _Synthesis()
    result = await _agent(docs, web, synthesis).run("công thức 145 là gì")
    assert result.outcome is AgentOutcome.ANSWERED
    assert 1 <= web.calls <= 2
    assert docs.calls <= 3
    assert result.synthesis.used_internal_knowledge is True
    assert "kiến thức nội tại" in result.answer
    assert result.synthesis.citations == ()


@pytest.mark.anyio
async def test_unconfigured_web_can_still_return_disclosed_internal_answer():
    synthesis = _Synthesis()
    result = await _agent(_Docs(), None, synthesis).run("công thức 145 là gì")
    assert result.outcome is AgentOutcome.ANSWERED
    assert result.synthesis.used_internal_knowledge is True
    assert result.synthesis.citations == ()


@pytest.mark.anyio
async def test_web_provider_error_during_required_fallback_is_not_silently_ignored():
    web = _Web(error=RuntimeError("provider unavailable"))
    result = await _agent(_Docs(), web, _Synthesis()).run("công thức 145 là gì")
    assert web.calls == 1
    assert result.outcome is AgentOutcome.FAILED


class _OrderedDocs(_Docs):
    def __init__(self, events, **kwargs):
        super().__init__(**kwargs)
        self.events = events

    async def search(self, question, budget):
        result = await super().search(question, budget)
        self.events.append("docs")
        return result


class _OrderedWeb(_Web):
    def __init__(self, events, **kwargs):
        super().__init__(**kwargs)
        self.events = events
        self.docs_calls_before_web = []

    async def search(self, question, budget):
        self.docs_calls_before_web.append(budget.snapshot().document_search_calls)
        result = await super().search(question, budget)
        self.events.append("web")
        return result


class _WebFirstModel(_EarlyFinishModel):
    async def _agenerate(self, messages, **kwargs):
        if not any(isinstance(item, ToolMessage) for item in messages):
            self.calls += 1
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{
                "name": "search_web", "args": {"query": "145 chord formula"},
                "id": f"web-first-{self.calls}", "type": "tool_call",
            }]))])
        return await super()._agenerate(messages, **kwargs)


class _AskDocsAfterWebModel(_WebFirstModel):
    async def _agenerate(self, messages, **kwargs):
        observations = [item for item in messages if isinstance(item, ToolMessage)]
        if len(observations) == 1:
            self.calls += 1
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{
                "name": "search_docs", "args": {"query": "145 chord formula"},
                "id": f"late-docs-{self.calls}", "type": "tool_call",
            }]))])
        if len(observations) == 2:
            self.calls += 1
            candidates = json.loads(observations[0].content).get("candidates", [])
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{
                "name": "select_context", "args": {"evidence_ids": [item["evidence_id"] for item in candidates]},
                "id": f"select-web-{self.calls}", "type": "tool_call",
            }]))])
        return await super()._agenerate(messages, **kwargs)


def _docs_first_agent(docs, web, synthesis, model=None):
    return MainAgent(dependencies=AgentGraphDependencies(
        document_search=docs, paragraph_selector=_Selector(), web_search=web,
        synthesizer=synthesis, orchestrator_model=model or _EarlyFinishModel(),
    ))


@pytest.mark.anyio
@pytest.mark.parametrize("empty_docs", [False, True])
async def test_docs_first_insufficient_evidence_exhausts_docs_before_web(empty_docs):
    events = []
    docs, web = _OrderedDocs(events, empty=empty_docs), _OrderedWeb(events)
    result = await _docs_first_agent(docs, web, _Synthesis()).run("công thức 145 là gì")
    assert result.outcome is AgentOutcome.ANSWERED
    assert docs.calls == 3
    assert web.docs_calls_before_web == [3]
    assert events == ["docs", "docs", "docs", "web"]
    assert result.synthesis.evidence_sufficient is True


@pytest.mark.anyio
async def test_docs_first_stops_when_second_document_search_is_sufficient():
    events = []
    docs, web = _OrderedDocs(events), _OrderedWeb(events)

    class SynthesisAfterSecondSearch(_Synthesis):
        async def synthesize(self, ledger, *, config=None):
            self.docs_sufficient = docs.calls >= 2
            return await super().synthesize(ledger, config=config)

    result = await _docs_first_agent(docs, web, SynthesisAfterSecondSearch()).run("công thức 145 là gì")
    assert result.outcome is AgentOutcome.ANSWERED
    assert events == ["docs", "docs"]
    assert web.calls == 0
    assert result.synthesis.evidence_sufficient is True


@pytest.mark.anyio
async def test_docs_first_premature_web_request_cannot_spend_web_quota():
    events = []
    docs, web = _OrderedDocs(events), _OrderedWeb(events)
    result = await _docs_first_agent(docs, web, _Synthesis(docs_sufficient=True), _WebFirstModel()).run(
        "công thức 145 là gì",
    )
    assert result.outcome is AgentOutcome.ANSWERED
    assert docs.calls == 1
    assert web.calls == 0
    assert result.budget.snapshot().web_search_calls == 0
    assert events == ["docs"]


@pytest.mark.anyio
@pytest.mark.parametrize("question", ["Tra web công thức 145 là gì", "Search web for the 145 chord formula"])
async def test_docs_first_explicit_web_request_skips_documents(question):
    events = []
    docs, web = _OrderedDocs(events), _OrderedWeb(events)
    result = await _docs_first_agent(docs, web, _Synthesis(), _WebFirstModel()).run(question)
    assert result.outcome is AgentOutcome.ANSWERED
    assert docs.calls == 0
    assert events == ["web"]
    assert web.docs_calls_before_web == [0]


@pytest.mark.anyio
async def test_docs_first_explicit_web_scope_rejects_later_document_calls():
    events = []
    docs, web = _OrderedDocs(events), _OrderedWeb(events)
    result = await _docs_first_agent(docs, web, _Synthesis(), _AskDocsAfterWebModel()).run(
        "Tra web thôi: công thức 145 là gì?",
    )
    assert result.outcome is AgentOutcome.ANSWERED
    assert docs.calls == 0
    assert events == ["web"]
    assert result.budget.snapshot().document_search_calls == 0


@pytest.mark.anyio
async def test_docs_first_without_web_exhausts_docs_before_internal_answer():
    docs, synthesis = _Docs(), _Synthesis()
    result = await _docs_first_agent(docs, None, synthesis).run("công thức 145 là gì")
    assert result.outcome is AgentOutcome.ANSWERED
    assert docs.calls == 3
    assert result.synthesis.used_internal_knowledge is True
    assert result.synthesis.citations == ()


@pytest.mark.anyio
async def test_docs_first_document_provider_error_is_a_real_failure():
    class FailedDocs(_Docs):
        async def search(self, question, budget):
            raise RuntimeError("document provider unavailable")

    web = _Web()
    result = await _docs_first_agent(FailedDocs(), web, _Synthesis()).run("công thức 145 là gì")
    assert result.outcome is AgentOutcome.FAILED
    assert web.calls == 0


def test_docs_first_synthesis_prefers_relevant_internal_evidence_and_uses_web_for_gaps():
    from saxophone.agent.prompts import SYNTHESIS_SYSTEM_PROMPT

    prompt = SYNTHESIS_SYSTEM_PROMPT.lower()
    assert "prefer internal document evidence" in prompt
    assert "equally relevant" in prompt
    assert "web evidence" in prompt
    assert "gaps" in prompt
    assert "do not force" in prompt
