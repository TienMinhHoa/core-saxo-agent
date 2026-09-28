"""Facade for invoking the compiled Main Agent graph."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from langchain_core.runnables import RunnableConfig

from .contracts import (
    AgentOutcome,
    AgentQuestion,
    ClarificationRequest,
    EvidenceLedger,
    RunBudget,
    SynthesisResult,
)
from .graph import AgentGraphDependencies, build_agent_graph
from .state import AgentGraphState, AgentStage


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    """Stable result returned by ``MainAgent.run``."""

    run_id: str
    outcome: AgentOutcome
    stage: AgentStage
    budget: RunBudget
    answer: str | None = None
    ledger: EvidenceLedger | None = None
    synthesis: SynthesisResult | None = None
    clarification: ClarificationRequest | None = None
    error: str | None = None
    state: AgentGraphState | None = None


class MainAgent:
    """Run one question through a compiled LangGraph state machine."""

    def __init__(
        self,
        *,
        document_search: object | None = None,
        document_search_tool: object | None = None,
        paragraph_selector: object | None = None,
        concept_selector: object | None = None,
        concept_role_selector: object | None = None,
        web_search: object | None = None,
        web_search_tool: object | None = None,
        synthesizer: object | None = None,
        answer_synthesizer: object | None = None,
        evidence_policy: object | None = None,
        strategy_policy: object | None = None,
        clarification_policy: object | None = None,
        ledger_factory: object | None = None,
        dependencies: AgentGraphDependencies | None = None,
        graph: object | None = None,
        checkpointer: object | None = None,
    ) -> None:
        document_search = _resolve_alias(
            document_search,
            document_search_tool,
            "document_search/document_search_tool",
        )
        concept_selector = _resolve_alias(
            concept_selector,
            concept_role_selector,
            "concept_selector/concept_role_selector",
        )
        web_search = _resolve_alias(
            web_search,
            web_search_tool,
            "web_search/web_search_tool",
        )
        synthesizer = _resolve_alias(
            synthesizer,
            answer_synthesizer,
            "synthesizer/answer_synthesizer",
        )
        supplied = any(
            value is not None
            for value in (
                document_search,
                paragraph_selector,
                concept_selector,
                web_search,
                synthesizer,
                evidence_policy,
                strategy_policy,
                clarification_policy,
                ledger_factory,
                dependencies,
            )
        )
        if graph is not None and supplied:
            raise ValueError("graph cannot be combined with graph dependencies")
        if graph is not None:
            if not callable(getattr(graph, "ainvoke", None)):
                raise TypeError("graph must provide ainvoke")
            self._graph = graph
        else:
            if dependencies is None:
                dependencies = AgentGraphDependencies(
                    document_search=document_search,
                    paragraph_selector=paragraph_selector,
                    concept_selector=concept_selector,
                    web_search=web_search,
                    synthesizer=synthesizer,
                    evidence_policy=evidence_policy,
                    strategy_policy=strategy_policy,
                    clarification_policy=clarification_policy,
                    ledger_factory=ledger_factory,
                )
            self._graph = build_agent_graph(dependencies, checkpointer=checkpointer)

    @property
    def graph(self) -> object:
        """Expose the compiled graph for composition and topology tests."""

        return self._graph

    async def run(
        self,
        question: AgentQuestion | str,
        *,
        run_id: str | None = None,
        budget: RunBudget | None = None,
        callbacks: object | None = None,
        config: RunnableConfig | None = None,
    ) -> AgentRunResult:
        if isinstance(question, str):
            question = AgentQuestion(question)
        if not isinstance(question, AgentQuestion):
            raise ValueError("question must be an AgentQuestion or non-blank string")
        normalized_run_id = (run_id or uuid4().hex).strip()
        if not normalized_run_id:
            raise ValueError("run_id must not be blank")
        run_budget = budget if budget is not None else RunBudget()
        if not isinstance(run_budget, RunBudget):
            raise TypeError("budget must be a RunBudget")

        run_config: RunnableConfig = dict(config or {})
        configurable = dict(run_config.get("configurable") or {})
        configurable["thread_id"] = normalized_run_id
        run_config["configurable"] = configurable
        if callbacks is not None:
            run_config["callbacks"] = callbacks
        try:
            state = await self._graph.ainvoke(
                {
                    "run_id": normalized_run_id,
                    "question": question,
                    "budget": run_budget,
                },
                config=run_config,
            )
        except BaseException as error:
            return AgentRunResult(
                normalized_run_id,
                AgentOutcome.FAILED,
                AgentStage.FAILED,
                run_budget,
                error=str(error) or error.__class__.__name__,
            )
        return _result_from_state(normalized_run_id, run_budget, state)

    execute = run


def _result_from_state(
    run_id: str, budget: RunBudget, state: object
) -> AgentRunResult:
    if not isinstance(state, dict):
        return AgentRunResult(run_id, AgentOutcome.FAILED, AgentStage.FAILED, budget)
    outcome = state.get("outcome", AgentOutcome.FAILED)
    stage = state.get("stage", AgentStage.FAILED)
    try:
        outcome = outcome if isinstance(outcome, AgentOutcome) else AgentOutcome(outcome)
    except (TypeError, ValueError):
        outcome = AgentOutcome.FAILED
    try:
        stage = stage if isinstance(stage, AgentStage) else AgentStage(stage)
    except (TypeError, ValueError):
        stage = AgentStage.FAILED
    return AgentRunResult(
        run_id=run_id,
        outcome=outcome,
        stage=stage,
        budget=state.get("budget", budget),
        answer=state.get("answer"),
        ledger=state.get("ledger"),
        synthesis=state.get("synthesis_result"),
        clarification=state.get("clarification"),
        error=state.get("error"),
        state=state,
    )


def _resolve_alias(primary: object | None, alias: object | None, name: str) -> object | None:
    if primary is not None and alias is not None:
        raise ValueError(f"pass only one of {name}")
    return primary if primary is not None else alias


__all__ = ["AgentRunResult", "MainAgent"]
