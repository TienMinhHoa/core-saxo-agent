"""Facade for invoking the compiled Main Agent graph."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
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
from .logging import (
    AgentLoggingCallbackHandler,
    log_agent_run_cancelled,
    log_agent_run_completed,
    log_agent_run_failed,
    log_agent_run_started,
)
from .langchain_callbacks import AgentTracingCallbackHandler
from .state import AgentGraphState, AgentStage
from .tracing import AgentTracer, NoopTracer, TraceStatus

BudgetFactory = Callable[[], RunBudget]


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
        orchestrator_policy: object | None = None,
        strategy_policy: object | None = None,
        clarification_policy: object | None = None,
        ledger_factory: object | None = None,
        dependencies: AgentGraphDependencies | None = None,
        graph: object | None = None,
        checkpointer: object | None = None,
        tracer: AgentTracer | None = None,
        budget_factory: BudgetFactory | None = None,
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
                orchestrator_policy,
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
                    orchestrator_policy=orchestrator_policy,
                    strategy_policy=strategy_policy,
                    clarification_policy=clarification_policy,
                    ledger_factory=ledger_factory,
                )
            self._graph = build_agent_graph(dependencies, checkpointer=checkpointer)
        self._tracer = tracer or NoopTracer()
        self._clarification_runs: dict[str, tuple[AgentQuestion, RunBudget, ClarificationRequest]] = {}
        if budget_factory is not None and not callable(budget_factory):
            raise TypeError("budget_factory must be callable")
        self._budget_factory = budget_factory if budget_factory is not None else RunBudget

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
        run_budget = budget if budget is not None else self._budget_factory()
        if not isinstance(run_budget, RunBudget):
            raise TypeError("budget must be a RunBudget")
        log_agent_run_started(run_id=normalized_run_id, question=question, budget=run_budget)

        run_config: RunnableConfig = dict(config or {})
        configurable = dict(run_config.get("configurable") or {})
        configurable["thread_id"] = normalized_run_id
        run_config["configurable"] = configurable
        trace = self._tracer.start_trace(
            run_id=normalized_run_id,
            name="agent_run",
            input={
                "question": question.question,
                "filters": dict(question.filters),
                "context_limit": question.context_limit,
            },
            metadata={"component": "main_agent"},
        )
        tracing_callback = AgentTracingCallbackHandler(
            run_id=normalized_run_id,
            tracer=self._tracer,
            root=trace,
        )
        logging_callback = AgentLoggingCallbackHandler(run_id=normalized_run_id)
        callback_list = _callback_list(callbacks)
        callback_list.append(tracing_callback)
        callback_list.append(logging_callback)
        run_config["callbacks"] = callback_list
        try:
            state = await self._graph.ainvoke(
                {
                    "run_id": normalized_run_id,
                    "question": question,
                    "budget": run_budget,
                },
                config=run_config,
            )
        except asyncio.CancelledError as error:
            log_agent_run_cancelled(run_id=normalized_run_id)
            tracing_callback.finish(error=error)
            trace.end(error=error)
            raise
        except BaseException as error:
            log_agent_run_failed(run_id=normalized_run_id, error=error)
            tracing_callback.finish(error=error)
            trace.end(error=error)
            return AgentRunResult(
                normalized_run_id,
                AgentOutcome.FAILED,
                AgentStage.FAILED,
                run_budget,
                error=str(error) or error.__class__.__name__,
            )
        result = _result_from_state(normalized_run_id, run_budget, state)
        if result.outcome is AgentOutcome.NEEDS_CLARIFICATION and result.clarification is not None:
            self._clarification_runs[normalized_run_id] = (
                question,
                run_budget,
                result.clarification,
            )
        else:
            self._clarification_runs.pop(normalized_run_id, None)
        tracing_callback.finish()
        if result.outcome is AgentOutcome.FAILED:
            log_agent_run_failed(run_id=normalized_run_id, error=RuntimeError(result.error or "agent_failed"), result=result)
        else:
            log_agent_run_completed(run_id=normalized_run_id, result=result)
        trace_output = {
            "outcome": result.outcome.value,
            "stage": result.stage.value,
            "used_tool_calls": result.budget.snapshot().used_tool_calls,
        }
        if result.outcome is AgentOutcome.FAILED:
            trace.end(
                status=TraceStatus.ERROR,
                output=trace_output,
                error_code="agent_failed",
            )
        else:
            trace.end(status=TraceStatus.OK, output=trace_output)
        return result

    execute = run

    async def resume(self, *, run_id: str, option: str) -> AgentRunResult:
        """Resume a clarification checkpoint without resetting its budget."""

        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must not be blank")
        if not isinstance(option, str) or not option.strip():
            raise ValueError("option must not be blank")
        get_state = getattr(self._graph, "aget_state", None)
        if not callable(get_state):
            raise ValueError("agent graph does not support resume")
        checkpoint = self._clarification_runs.get(run_id.strip())
        if checkpoint is None:
            raise ValueError("run is not waiting for clarification")
        question, budget, clarification = checkpoint
        normalized_option = option.strip()
        if normalized_option not in clarification.options:
            raise ValueError("option is not one of the clarification choices")
        resumed_question = AgentQuestion(
            f"{question.question}\nSelected interpretation: {normalized_option}",
            filters=question.filters,
            context_limit=question.context_limit,
            history=question.history,
        )
        return await self.run(resumed_question, run_id=run_id, budget=budget)


def _callback_list(callbacks: object | None) -> list[object]:
    """Normalize optional callback input before appending the tracing bridge."""

    if callbacks is None:
        return []
    if isinstance(callbacks, (list, tuple)):
        return list(callbacks)
    return [callbacks]


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
