from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from langchain_core.callbacks import BaseCallbackHandler

from saxophone.agent.contracts import (
    AgentOutcome,
    AgentQuestion,
    Citation,
    EvidenceLedger,
    RunBudget,
    SelectionStrategy,
    SynthesisResult,
)
from saxophone.agent.document_search import DocumentSearchResult, DocumentSearchStatus
from saxophone.agent.evidence_selection import SelectionRequest, SelectionResult
from saxophone.agent.graph import AgentGraphDependencies, build_agent_graph
from saxophone.agent.langchain_tools import create_document_search_tool
from saxophone.agent.orchestrator import MainAgent
from saxophone.agent.state import AgentStage
from saxophone.agent.tracing import InMemoryTracer, TraceStatus
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.renderers import AnswerContextModel, SourceParagraph


def _hit(chunk_ref: str = "chunk-1") -> ChunkHit:
    return ChunkHit(
        "music.md",
        chunk_ref,
        1,
        "retrieval-v1",
        {"document_ref": "music-book", "source_version": "source-v1"},
        semantic_score=0.9,
    )


def _paragraph(ref: str = "paragraph-1", chunk: str = "chunk-1") -> SourceParagraph:
    return SourceParagraph(
        ref,
        "music.md",
        "Major triads",
        (),
        "A major triad has a root, third, and fifth.",
        ("Major triad -> Definition",),
        ("121",),
        (),
        chunk,
    )


class _DocumentSearch:
    name = "document_search"

    def __init__(self, result: DocumentSearchResult) -> None:
        self.result = result
        self.calls: list[tuple[AgentQuestion, RunBudget]] = []

    async def search(self, question: AgentQuestion, budget: RunBudget) -> DocumentSearchResult:
        self.calls.append((question, budget))
        return self.result


class _Selector:
    def __init__(self, strategy: SelectionStrategy, paragraph: SourceParagraph) -> None:
        self.strategy = strategy
        self.paragraph = paragraph
        self.calls: list[SelectionRequest] = []

    async def select(self, request: SelectionRequest) -> SelectionResult:
        self.calls.append(request)
        return SelectionResult(
            self.strategy,
            AnswerContextModel((), (self.paragraph,), (self.paragraph.paragraph_ref,)),
        )


class _Synthesizer:
    def __init__(self) -> None:
        self.ledgers: list[EvidenceLedger] = []

    async def synthesize(self, ledger: EvidenceLedger) -> SynthesisResult:
        self.ledgers.append(ledger)
        if not ledger.evidence:
            return SynthesisResult(answer="No grounded evidence was found.")
        evidence_id = ledger.evidence[0].evidence_id
        return SynthesisResult(
            answer="A major triad uses a root, third, and fifth.",
            used_evidence_ids=(evidence_id,),
            citations=(Citation(evidence_id, "[1]"),),
        )


class _ToolCallbackRecorder(BaseCallbackHandler):
    def __init__(self) -> None:
        self.started: list[dict[str, object]] = []

    def on_tool_start(self, serialized, input_str, **kwargs):  # type: ignore[no-untyped-def]
        self.started.append(dict(kwargs.get("inputs") or {}))


class _ConfigAwareSearch:
    name = "document_search"

    def __init__(self, result: DocumentSearchResult) -> None:
        self.result = result
        self.configs: list[object] = []

    async def ainvoke(self, payload: object, *, config: object) -> DocumentSearchResult:
        del payload
        self.configs.append(config)
        return self.result


@dataclass(frozen=True, slots=True)
class _WebResult:
    query: str
    items: tuple[object, ...]


class _WebSearch:
    name = "web_search"

    def __init__(self) -> None:
        self.calls: list[tuple[AgentQuestion, RunBudget]] = []

    async def search(self, question: AgentQuestion, budget: RunBudget) -> _WebResult:
        self.calls.append((question, budget))
        return _WebResult(question.question, (object(),))


@pytest.mark.anyio
async def test_main_agent_runs_compiled_langgraph_for_local_evidence() -> None:
    paragraph = _paragraph()
    search = _DocumentSearch(
        DocumentSearchResult(
            "What is a major triad?",
            (_hit(),),
            (paragraph,),
            status=DocumentSearchStatus.READY,
        )
    )
    selector = _Selector(SelectionStrategy.PARAGRAPH_DIRECT, paragraph)
    synthesizer = _Synthesizer()
    agent = MainAgent(
        document_search=search,
        paragraph_selector=selector,
        synthesizer=synthesizer,
    )

    result = await agent.run(AgentQuestion("What is a major triad?"), run_id="run-local")

    assert result.outcome is AgentOutcome.ANSWERED
    assert result.stage is AgentStage.COMPLETED
    assert result.answer == "A major triad uses a root, third, and fifth."
    assert len(search.calls) == 1
    assert search.calls[0][1] is result.budget
    assert len(selector.calls) == 1
    assert len(synthesizer.ledgers) == 1
    assert result.run_id == "run-local"


@pytest.mark.anyio
async def test_orchestrator_policy_can_route_local_observation_to_web_then_synthesis() -> None:
    paragraph = _paragraph()
    search = _DocumentSearch(
        DocumentSearchResult(
            "Công thức 145 là gì?",
            (_hit(),),
            (paragraph,),
            status=DocumentSearchStatus.READY,
        )
    )
    selector = _Selector(SelectionStrategy.PARAGRAPH_DIRECT, paragraph)
    web = _WebSearch()
    synthesizer = _Synthesizer()
    decisions: list[AgentStage] = []

    async def orchestrator_policy(state):
        stage = state.get("stage")
        decisions.append(stage)
        if stage is AgentStage.EVALUATING_EVIDENCE:
            return "web"
        return "synthesize"

    agent = MainAgent(
        document_search=search,
        paragraph_selector=selector,
        web_search=web,
        synthesizer=synthesizer,
        orchestrator_policy=orchestrator_policy,
    )

    result = await agent.run("Công thức 145 là gì?", run_id="run-orchestrated")

    assert result.outcome is AgentOutcome.ANSWERED
    assert len(web.calls) == 1
    assert len(synthesizer.ledgers) == 1
    assert AgentStage.EVALUATING_EVIDENCE in decisions
    assert AgentStage.WEB_SEARCHING in decisions


@pytest.mark.anyio
@pytest.mark.parametrize("question_text", [
    "Hãy tra web và trả lời cho tôi công thức 145 là gì",
    "Hãy tra wweb và trả lời cho tôi công thức 145 là gì",
    "Search the web for formula 145",
])
async def test_explicit_web_request_skips_local_search(question_text: str) -> None:
    search = _DocumentSearch(DocumentSearchResult(question_text, (), (), status=DocumentSearchStatus.NO_HITS))
    web = _WebSearch()
    agent = MainAgent(document_search=search, web_search=web)

    await agent.run(question_text, run_id="explicit-web")

    assert search.calls == []
    assert len(web.calls) == 1


@pytest.mark.anyio
async def test_explicit_web_request_without_provider_reports_missing_web_search() -> None:
    request = "Tra web về công thức 145"
    search = _DocumentSearch(DocumentSearchResult(request, (), (), status=DocumentSearchStatus.NO_HITS))
    agent = MainAgent(document_search=search)

    result = await agent.run(request, run_id="missing-web")

    assert search.calls == []
    assert result.outcome is AgentOutcome.INSUFFICIENT_EVIDENCE
    assert result.state["reason_code"] == "web search is not configured"


@pytest.mark.anyio
async def test_main_agent_propagates_document_search_cancellation_and_closes_trace() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingSearch:
        async def search(self, question: AgentQuestion, budget: RunBudget) -> DocumentSearchResult:
            del question, budget
            started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            raise AssertionError("blocking search should not return")

    tracer = InMemoryTracer()
    agent = MainAgent(document_search=BlockingSearch(), tracer=tracer)
    task = asyncio.create_task(agent.run("question", run_id="run-cancelled"))

    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert cancelled.is_set()
    assert tracer.records[0].status is TraceStatus.ERROR
    assert tracer.records[0].ended_at is not None


@pytest.mark.anyio
async def test_main_agent_builds_a_fresh_budget_from_the_configured_factory() -> None:
    budgets: list[RunBudget] = []

    def budget_factory() -> RunBudget:
        budget = RunBudget(
            max_tool_calls=1,
            max_document_search_calls=1,
            max_web_search_calls=1,
            max_hits_per_tool=2,
            tool_timeout_seconds=3,
            max_context_tokens=120,
        )
        budgets.append(budget)
        return budget

    search = _DocumentSearch(
        DocumentSearchResult("question", status=DocumentSearchStatus.NO_HITS)
    )
    agent = MainAgent(document_search=search, budget_factory=budget_factory)

    first = await agent.run(AgentQuestion("question"), run_id="run-budget-1")
    second = await agent.run(AgentQuestion("question"), run_id="run-budget-2")

    assert first.budget is budgets[0]
    assert second.budget is budgets[1]
    assert first.budget is not second.budget
    assert first.budget.snapshot().max_tool_calls == 1
    assert first.budget.snapshot().max_context_tokens == 120


@pytest.mark.anyio
async def test_main_agent_explicit_budget_overrides_the_factory() -> None:
    factory_calls = 0

    def budget_factory() -> RunBudget:
        nonlocal factory_calls
        factory_calls += 1
        return RunBudget(max_tool_calls=1)

    search = _DocumentSearch(
        DocumentSearchResult("question", status=DocumentSearchStatus.NO_HITS)
    )
    agent = MainAgent(document_search=search, budget_factory=budget_factory)
    explicit = RunBudget(max_tool_calls=4)

    result = await agent.run(
        AgentQuestion("question"), run_id="run-budget-explicit", budget=explicit
    )

    assert result.budget is explicit
    assert factory_calls == 0


@pytest.mark.anyio
async def test_main_agent_forwards_runtime_callbacks_to_langchain_document_tool() -> None:
    paragraph = _paragraph()
    adapter = _DocumentSearch(
        DocumentSearchResult(
            "What is a major triad?",
            (_hit(),),
            (paragraph,),
            status=DocumentSearchStatus.READY,
        )
    )
    tool = create_document_search_tool(adapter)
    recorder = _ToolCallbackRecorder()

    agent = MainAgent(
        document_search=tool,
        paragraph_selector=_Selector(SelectionStrategy.PARAGRAPH_DIRECT, paragraph),
        synthesizer=_Synthesizer(),
    )

    result = await agent.run(
        AgentQuestion("What is a major triad?"),
        run_id="run-langchain-tool",
        callbacks=recorder,
    )

    assert result.outcome is AgentOutcome.ANSWERED
    assert recorder.started == [
        {"question": "What is a major triad?", "filters": {}, "context_limit": 12_000}
    ]


@pytest.mark.anyio
async def test_graph_passes_runnable_config_to_ainvoke_only_search_tools() -> None:
    search = _ConfigAwareSearch(
        DocumentSearchResult("question", status=DocumentSearchStatus.NO_HITS)
    )
    graph = build_agent_graph(AgentGraphDependencies(document_search=search))
    callback = _ToolCallbackRecorder()

    state = await graph.ainvoke(
        {"question": AgentQuestion("question"), "run_id": "run-config"},
        config={"callbacks": [callback], "configurable": {"thread_id": "run-config"}},
    )

    assert state["outcome"] is AgentOutcome.INSUFFICIENT_EVIDENCE
    assert len(search.configs) == 1
    assert isinstance(search.configs[0], dict)
    assert search.configs[0]["callbacks"]


@pytest.mark.anyio
async def test_graph_uses_web_fallback_when_local_search_is_empty() -> None:
    search = _DocumentSearch(
        DocumentSearchResult("What is a major triad?", status=DocumentSearchStatus.NO_HITS)
    )
    web = _WebSearch()
    dependencies = AgentGraphDependencies(document_search=search, web_search=web)
    graph = build_agent_graph(dependencies)

    state = await graph.ainvoke(
        {"question": AgentQuestion("What is a major triad?"), "run_id": "run-web"},
        config={"configurable": {"thread_id": "run-web"}},
    )

    assert state["stage"] is AgentStage.COMPLETED
    assert state["outcome"] is AgentOutcome.INSUFFICIENT_EVIDENCE
    assert len(web.calls) == 1


@pytest.mark.anyio
async def test_graph_can_stop_for_clarification_before_synthesis() -> None:
    paragraph = _paragraph()
    search = _DocumentSearch(
        DocumentSearchResult(
            "Which triad?",
            (_hit(),),
            (paragraph,),
            status=DocumentSearchStatus.READY,
        )
    )
    synthesizer = _Synthesizer()
    agent = MainAgent(
        document_search=search,
        paragraph_selector=_Selector(SelectionStrategy.PARAGRAPH_DIRECT, paragraph),
        synthesizer=synthesizer,
        clarification_policy=lambda _state: ("Which triad do you mean?", ("major", "minor")),
    )

    result = await agent.run(AgentQuestion("Which triad?"), run_id="run-clarify")

    assert result.outcome is AgentOutcome.NEEDS_CLARIFICATION
    assert result.stage is AgentStage.WAITING_FOR_CLARIFICATION
    assert result.clarification is not None
    assert result.clarification.options == ("major", "minor")
    assert synthesizer.ledgers == []


def test_compiled_graph_exposes_required_nodes_and_edges() -> None:
    graph = build_agent_graph(
        AgentGraphDependencies(document_search=_DocumentSearch(DocumentSearchResult("q")))
    )

    node_names = set(graph.get_graph().nodes)
    assert {
        "receive_question",
        "document_search_tool",
        "evaluate_local_evidence",
        "choose_selection_strategy",
        "select_evidence",
        "web_search_tool",
        "needs_clarification",
        "synthesize",
        "validate_answer",
        "completed",
        "failed",
    } <= node_names
