"""LangGraph implementation of the Main Agent orchestration flow."""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Sequence
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

from .contracts import (
    AgentOutcome,
    AgentQuestion,
    BudgetExhaustedError,
    ClarificationRequest,
    EvidenceLedger,
    RunBudget,
    SelectionStrategy,
    SynthesisResult,
    WebSearchResult,
)
from .document_search import DocumentSearchResult, DocumentSearchStatus
from .evidence import EvidenceLedgerBuilder
from .evidence_selection import SelectionRequest, SelectionResult
from .ports import AnswerSynthesizer, DocumentSearchTool, EvidenceSelector, WebSearchTool
from .state import AgentDecision, AgentGraphState, AgentStage


class GraphDependencyError(TypeError):
    """Raised when a graph dependency does not satisfy its typed boundary."""


EvidencePolicy = Callable[[AgentGraphState], object]
StrategyPolicy = Callable[[DocumentSearchResult], SelectionStrategy | str]
ClarificationPolicy = Callable[[AgentGraphState], object]
LedgerFactory = Callable[[AgentGraphState], EvidenceLedger]


@dataclass(frozen=True, slots=True)
class AgentGraphDependencies:
    """Ports and policies injected into the compiled graph."""

    document_search: DocumentSearchTool
    paragraph_selector: EvidenceSelector | None = None
    concept_selector: EvidenceSelector | None = None
    web_search: WebSearchTool | None = None
    synthesizer: AnswerSynthesizer | None = None
    evidence_policy: EvidencePolicy | None = None
    strategy_policy: StrategyPolicy | None = None
    clarification_policy: ClarificationPolicy | None = None
    ledger_factory: LedgerFactory | None = None

    def __post_init__(self) -> None:
        if not _has_search_entrypoint(self.document_search):
            raise GraphDependencyError("document_search must provide async search")
        if self.web_search is not None and not _has_search_entrypoint(self.web_search):
            raise GraphDependencyError("web_search must provide async search")
        if self.synthesizer is not None and not (
            callable(getattr(self.synthesizer, "synthesize", None))
            or callable(getattr(self.synthesizer, "ainvoke", None))
        ):
            raise GraphDependencyError("synthesizer must provide async synthesize")
        for name, selector in (
            ("paragraph_selector", self.paragraph_selector),
            ("concept_selector", self.concept_selector),
        ):
            if selector is not None and not callable(getattr(selector, "select", None)):
                raise GraphDependencyError(f"{name} must provide async select")
        for name, policy in (
            ("evidence_policy", self.evidence_policy),
            ("strategy_policy", self.strategy_policy),
            ("clarification_policy", self.clarification_policy),
            ("ledger_factory", self.ledger_factory),
        ):
            if policy is not None and not callable(policy):
                raise GraphDependencyError(f"{name} must be callable")


def build_agent_graph(
    dependencies: AgentGraphDependencies | None = None,
    *,
    checkpointer: object | None = None,
    document_search: object | None = None,
    paragraph_selector: object | None = None,
    concept_selector: object | None = None,
    web_search: object | None = None,
    synthesizer: object | None = None,
    evidence_policy: EvidencePolicy | None = None,
    strategy_policy: StrategyPolicy | None = None,
    clarification_policy: ClarificationPolicy | None = None,
    ledger_factory: LedgerFactory | None = None,
):
    """Build and compile the Main Agent graph once for application injection."""

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
    elif not isinstance(dependencies, AgentGraphDependencies):
        raise TypeError("dependencies must be AgentGraphDependencies")

    graph = StateGraph(AgentGraphState)
    graph.add_node("receive_question", _receive_question)
    graph.add_node("document_search_tool", _document_search_tool(dependencies))
    graph.add_node("evaluate_local_evidence", _evaluate_local_evidence(dependencies))
    graph.add_node("choose_selection_strategy", _choose_selection_strategy(dependencies))
    graph.add_node("select_evidence", _select_evidence(dependencies))
    graph.add_node("web_search_tool", _web_search_tool(dependencies))
    graph.add_node("needs_clarification", _needs_clarification)
    graph.add_node("synthesize", _synthesize(dependencies))
    graph.add_node("validate_answer", _validate_answer)
    graph.add_node("completed", _completed)
    graph.add_node("failed", _failed)

    graph.add_edge(START, "receive_question")
    graph.add_edge("receive_question", "document_search_tool")
    graph.add_edge("document_search_tool", "evaluate_local_evidence")
    graph.add_conditional_edges(
        "evaluate_local_evidence",
        _route_decision,
        {
            AgentDecision.SELECT: "choose_selection_strategy",
            AgentDecision.WEB: "web_search_tool",
            AgentDecision.CLARIFY: "needs_clarification",
            AgentDecision.INSUFFICIENT: "completed",
            AgentDecision.FAILED: "failed",
        },
    )
    graph.add_edge("choose_selection_strategy", "select_evidence")
    graph.add_conditional_edges(
        "select_evidence",
        _route_decision,
        {
            AgentDecision.SYNTHESIZE: "synthesize",
            AgentDecision.WEB: "web_search_tool",
            AgentDecision.CLARIFY: "needs_clarification",
            AgentDecision.INSUFFICIENT: "completed",
            AgentDecision.FAILED: "failed",
        },
    )
    graph.add_conditional_edges(
        "web_search_tool",
        _route_decision,
        {
            AgentDecision.SYNTHESIZE: "synthesize",
            AgentDecision.CLARIFY: "needs_clarification",
            AgentDecision.INSUFFICIENT: "completed",
            AgentDecision.FAILED: "failed",
        },
    )
    graph.add_edge("needs_clarification", "completed")
    graph.add_conditional_edges(
        "synthesize",
        _route_decision,
        {
            AgentDecision.VALIDATE: "validate_answer",
            AgentDecision.INSUFFICIENT: "completed",
            AgentDecision.FAILED: "failed",
        },
    )
    graph.add_conditional_edges(
        "validate_answer",
        _route_decision,
        {
            AgentDecision.COMPLETE: "completed",
            AgentDecision.FAILED: "failed",
        },
    )
    graph.add_edge("completed", END)
    graph.add_edge("failed", END)

    # MainAgent supplies a thread id for every invocation, allowing this
    # default saver to support clarification resume without recompiling.
    saver = (
        checkpointer
        if checkpointer is not None
        else MemorySaver(serde=_RuntimeSerializer())
    )
    return graph.compile(checkpointer=saver)


class _RuntimeSerializer:
    """Serialize ordinary values and retain domain DTOs in this process.

    LangGraph's default msgpack serializer intentionally rejects objects such
    as ``RunBudget`` (which owns a lock) and immutable mapping proxies.  The
    application checkpointer is in-memory during this migration, so retaining
    those typed values behind opaque tokens preserves checkpoint/resume within
    the process without flattening domain contracts into untyped dictionaries.
    """

    def __init__(self) -> None:
        self._fallback = JsonPlusSerializer(pickle_fallback=True)
        self._runtime: dict[bytes, object] = {}

    def dumps_typed(self, value: object) -> tuple[str, bytes]:
        try:
            return self._fallback.dumps_typed(value)
        except (TypeError, ValueError, AttributeError):
            token = uuid4().hex.encode("ascii")
            self._runtime[token] = value
            return "runtime", token

    def loads_typed(self, payload: tuple[str, bytes]) -> object:
        type_name, data = payload
        if type_name == "runtime":
            return self._runtime[data]
        return self._fallback.loads_typed(payload)


async def _receive_question(state: AgentGraphState) -> AgentGraphState:
    question = state.get("question")
    if isinstance(question, str):
        question = AgentQuestion(question)
    if not isinstance(question, AgentQuestion):
        return _failure("question must be an AgentQuestion")
    budget = state.get("budget")
    if not isinstance(budget, RunBudget):
        budget = RunBudget()
    run_id = state.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        return _failure("run_id must be a non-empty string")
    return {
        "question": question,
        "budget": budget,
        "run_id": run_id.strip(),
        "stage": AgentStage.RECEIVED,
        "outcome": None,
        "decision": AgentDecision.SELECT,
    }


def _document_search_tool(dependencies: AgentGraphDependencies):
    async def node(state: AgentGraphState) -> AgentGraphState:
        question = state.get("question")
        budget = state.get("budget")
        if not isinstance(question, AgentQuestion) or not isinstance(budget, RunBudget):
            return _failure("graph received invalid question or budget")
        try:
            result = await _invoke_search(dependencies.document_search, question, budget)
            if not isinstance(result, DocumentSearchResult):
                raise TypeError("document search must return DocumentSearchResult")
        except BudgetExhaustedError as error:
            return _budget_failure(error)
        except BaseException as error:
            return _failure(_safe_error(error))
        return {
            "document_result": result,
            "stage": AgentStage.DOCUMENT_SEARCHING,
            "decision": AgentDecision.SELECT,
        }

    return node


def _evaluate_local_evidence(dependencies: AgentGraphDependencies):
    async def node(state: AgentGraphState) -> AgentGraphState:
        result = state.get("document_result")
        if not isinstance(result, DocumentSearchResult):
            return _failure("document search result is missing")

        if dependencies.clarification_policy is not None:
            clarification = await _await_result(dependencies.clarification_policy(state))
            request = _coerce_clarification(clarification, state)
            if request is not None:
                return {
                    "clarification": request,
                    "stage": AgentStage.EVALUATING_EVIDENCE,
                    "decision": AgentDecision.CLARIFY,
                    "reason_code": request.reason_code,
                }

        decision = None
        if dependencies.evidence_policy is not None:
            decision = _coerce_decision(
                await _await_result(dependencies.evidence_policy(state))
            )
        if decision is None:
            if result.status is DocumentSearchStatus.READY:
                decision = AgentDecision.SELECT
            elif dependencies.web_search is not None:
                decision = AgentDecision.WEB
            else:
                decision = AgentDecision.INSUFFICIENT
        return {
            "stage": AgentStage.EVALUATING_EVIDENCE,
            "decision": decision,
            "outcome": (
                AgentOutcome.INSUFFICIENT_EVIDENCE
                if decision is AgentDecision.INSUFFICIENT
                else None
            ),
            "reason_code": _reason_for_decision(decision),
        }

    return node


def _choose_selection_strategy(dependencies: AgentGraphDependencies):
    async def node(state: AgentGraphState) -> AgentGraphState:
        result = state.get("document_result")
        if not isinstance(result, DocumentSearchResult):
            return _failure("document search result is missing")
        if dependencies.strategy_policy is not None:
            raw_strategy = await _await_result(dependencies.strategy_policy(result))
            try:
                strategy = SelectionStrategy(raw_strategy)
            except (TypeError, ValueError) as error:
                return _failure(f"invalid selection strategy: {error}")
        elif result.relations and dependencies.concept_selector is not None:
            strategy = SelectionStrategy.CONCEPT_ROLE
        else:
            strategy = SelectionStrategy.PARAGRAPH_DIRECT
        return {
            "selection_strategy": strategy,
            "stage": AgentStage.SELECTING_EVIDENCE,
            "decision": AgentDecision.SYNTHESIZE,
        }

    return node


def _select_evidence(dependencies: AgentGraphDependencies):
    async def node(state: AgentGraphState) -> AgentGraphState:
        question = state.get("question")
        result = state.get("document_result")
        strategy = state.get("selection_strategy")
        if not isinstance(question, AgentQuestion) or not isinstance(
            result, DocumentSearchResult
        ):
            return _failure("selection received incomplete graph state")
        if not isinstance(strategy, SelectionStrategy):
            return _failure("selection strategy is missing")
        selector = (
            dependencies.concept_selector
            if strategy is SelectionStrategy.CONCEPT_ROLE
            else dependencies.paragraph_selector
        )
        if selector is None:
            return _failure(f"no selector configured for {strategy.value}")
        request = SelectionRequest(question, result)
        try:
            selected = await _invoke_selector(selector, request)
            if not isinstance(selected, SelectionResult):
                raise TypeError("evidence selector must return SelectionResult")
            selected.validate_against(request)
        except BaseException as error:
            return _failure(_safe_error(error))
        if not selected.selected_paragraph_refs:
            if dependencies.web_search is not None:
                decision = AgentDecision.WEB
            else:
                decision = AgentDecision.INSUFFICIENT
            return {
                "selection_result": selected,
                "stage": AgentStage.SELECTING_EVIDENCE,
                "decision": decision,
                "outcome": (
                    AgentOutcome.INSUFFICIENT_EVIDENCE
                    if decision is AgentDecision.INSUFFICIENT
                    else None
                ),
            }
        return {
            "selection_result": selected,
            "stage": AgentStage.SELECTING_EVIDENCE,
            "decision": AgentDecision.SYNTHESIZE,
        }

    return node


def _web_search_tool(dependencies: AgentGraphDependencies):
    async def node(state: AgentGraphState) -> AgentGraphState:
        question = state.get("question")
        budget = state.get("budget")
        if dependencies.web_search is None:
            return _insufficient("web search is not configured")
        if not isinstance(question, AgentQuestion) or not isinstance(budget, RunBudget):
            return _failure("web search received invalid question or budget")
        try:
            result = await _invoke_search(dependencies.web_search, question, budget)
        except BudgetExhaustedError as error:
            return _budget_failure(error)
        except BaseException as error:
            return _failure(_safe_error(error))
        if not _has_web_evidence(result):
            return _insufficient("web search returned no evidence")
        return {
            "web_result": result,
            "stage": AgentStage.WEB_SEARCHING,
            "decision": AgentDecision.SYNTHESIZE,
            "reason_code": "web_evidence_available",
        }

    return node


async def _needs_clarification(state: AgentGraphState) -> AgentGraphState:
    request = state.get("clarification")
    if not isinstance(request, ClarificationRequest):
        return _failure("clarification request is missing")
    return {
        "stage": AgentStage.WAITING_FOR_CLARIFICATION,
        "outcome": AgentOutcome.NEEDS_CLARIFICATION,
        "decision": AgentDecision.COMPLETE,
    }


def _synthesize(dependencies: AgentGraphDependencies):
    async def node(state: AgentGraphState) -> AgentGraphState:
        if dependencies.synthesizer is None:
            return _insufficient("answer synthesizer is not configured")
        try:
            ledger = (
                await _await_result(dependencies.ledger_factory(state))
                if dependencies.ledger_factory is not None
                else _default_ledger(state)
            )
            if not isinstance(ledger, EvidenceLedger):
                raise TypeError("ledger factory must return EvidenceLedger")
            result = await _invoke_synthesizer(dependencies.synthesizer, ledger)
            synthesis = _coerce_synthesis(result)
        except BudgetExhaustedError as error:
            return _budget_failure(error)
        except BaseException as error:
            return _failure(_safe_error(error))
        return {
            "ledger": ledger,
            "synthesis_result": synthesis,
            "answer": synthesis.answer,
            "stage": AgentStage.SYNTHESIZING,
            "decision": AgentDecision.VALIDATE,
        }

    return node


async def _validate_answer(state: AgentGraphState) -> AgentGraphState:
    ledger = state.get("ledger")
    synthesis = state.get("synthesis_result")
    if not isinstance(ledger, EvidenceLedger) or not isinstance(synthesis, SynthesisResult):
        return _failure("synthesis output is incomplete")
    try:
        synthesis.validate_against(ledger)
    except BaseException as error:
        return _failure(_safe_error(error))
    return {
        "decision": AgentDecision.COMPLETE,
        "outcome": AgentOutcome.ANSWERED,
        "stage": AgentStage.SYNTHESIZING,
    }


async def _completed(state: AgentGraphState) -> AgentGraphState:
    outcome = state.get("outcome")
    if outcome is None:
        outcome = AgentOutcome.INSUFFICIENT_EVIDENCE
    terminal_stage = (
        AgentStage.WAITING_FOR_CLARIFICATION
        if outcome is AgentOutcome.NEEDS_CLARIFICATION
        else AgentStage.COMPLETED
    )
    return {"stage": terminal_stage, "outcome": outcome}


async def _failed(state: AgentGraphState) -> AgentGraphState:
    outcome = state.get("outcome")
    if outcome not in {AgentOutcome.BUDGET_EXHAUSTED, AgentOutcome.FAILED}:
        outcome = AgentOutcome.FAILED
    return {"stage": AgentStage.FAILED, "outcome": outcome}


def _route_decision(state: AgentGraphState) -> AgentDecision:
    decision = state.get("decision", AgentDecision.FAILED)
    if isinstance(decision, AgentDecision):
        return decision
    try:
        return AgentDecision(decision)
    except (TypeError, ValueError):
        return AgentDecision.FAILED


def _failure(message: str) -> AgentGraphState:
    return {
        "stage": AgentStage.FAILED,
        "outcome": AgentOutcome.FAILED,
        "decision": AgentDecision.FAILED,
        "error": message,
    }


def _budget_failure(error: BudgetExhaustedError) -> AgentGraphState:
    return {
        "stage": AgentStage.FAILED,
        "outcome": AgentOutcome.BUDGET_EXHAUSTED,
        "decision": AgentDecision.FAILED,
        "error": str(error),
        "reason_code": error.reason,
    }


def _insufficient(reason: str) -> AgentGraphState:
    return {
        "stage": AgentStage.EVALUATING_EVIDENCE,
        "outcome": AgentOutcome.INSUFFICIENT_EVIDENCE,
        "decision": AgentDecision.INSUFFICIENT,
        "reason_code": reason,
    }


async def _await_result(value: Awaitable[Any] | Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _has_search_entrypoint(tool: object) -> bool:
    return callable(getattr(tool, "search", None)) or callable(
        getattr(tool, "ainvoke", None)
    )


async def _invoke_search(tool: object, question: AgentQuestion, budget: RunBudget) -> object:
    search = getattr(tool, "search", None)
    if callable(search):
        return await _await_result(search(question, budget))
    invoke = getattr(tool, "ainvoke", None)
    if not callable(invoke):
        raise TypeError("search tool must provide search or ainvoke")
    payload = {"question": question.question, "budget": budget}
    try:
        return await _await_result(invoke(payload))
    except TypeError:
        return await _await_result(invoke(question.question))


async def _invoke_selector(selector: object, request: SelectionRequest) -> object:
    select = getattr(selector, "select", None)
    if callable(select):
        return await _await_result(select(request))
    invoke = getattr(selector, "ainvoke", None)
    if callable(invoke):
        return await _await_result(invoke(request))
    raise TypeError("evidence selector must provide select or ainvoke")


async def _invoke_synthesizer(synthesizer: object, ledger: EvidenceLedger) -> object:
    synthesize = getattr(synthesizer, "synthesize", None)
    if callable(synthesize):
        return await _await_result(synthesize(ledger))
    invoke = getattr(synthesizer, "ainvoke", None)
    if callable(invoke):
        return await _await_result(invoke(ledger))
    raise TypeError("synthesizer must provide synthesize or ainvoke")


def _coerce_decision(value: object) -> AgentDecision | None:
    if value is None:
        return None
    if isinstance(value, AgentDecision):
        return value
    if isinstance(value, str):
        aliases = {
            "select_evidence": AgentDecision.SELECT,
            "search_web": AgentDecision.WEB,
            "needs_clarification": AgentDecision.CLARIFY,
            "insufficient_evidence": AgentDecision.INSUFFICIENT,
        }
        if value in aliases:
            return aliases[value]
        return AgentDecision(value)
    return None


def _coerce_clarification(value: object, state: AgentGraphState) -> ClarificationRequest | None:
    if value is None or value is False:
        return None
    if isinstance(value, ClarificationRequest):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        question, options = value
        if (
            isinstance(question, str)
            and isinstance(options, Sequence)
            and not isinstance(options, (str, bytes))
        ):
            return ClarificationRequest(
                question,
                tuple(str(option) for option in options),
                "ambiguous_interpretation",
            )
    if value is True:
        question = state.get("question")
        if isinstance(question, AgentQuestion):
            return ClarificationRequest(
                question.question,
                ("Please clarify the intended interpretation.",),
                "ambiguous_interpretation",
            )
    return None


def _coerce_synthesis(value: object) -> SynthesisResult:
    if isinstance(value, SynthesisResult):
        return value
    answer = getattr(value, "answer", None)
    if not isinstance(answer, str):
        raise TypeError("synthesizer must return SynthesisResult")
    return SynthesisResult(
        answer,
        tuple(getattr(value, "used_evidence_ids", ())),
        tuple(getattr(value, "citations", ())),
        tuple(getattr(value, "image_evidence_ids", ())),
    )


def _default_ledger(state: AgentGraphState) -> EvidenceLedger:
    question = state.get("question")
    selection = state.get("selection_result")
    strategy = state.get("selection_strategy", SelectionStrategy.PARAGRAPH_DIRECT)
    if not isinstance(question, AgentQuestion):
        raise ValueError("question is required to build an evidence ledger")
    if not isinstance(strategy, SelectionStrategy):
        strategy = SelectionStrategy(strategy)
    paragraphs = selection.paragraphs if isinstance(selection, SelectionResult) else ()
    builder = EvidenceLedgerBuilder(
        run_id=state.get("run_id", "agent-run"),
        question=question,
        selected_strategy=strategy,
    )
    document_result = state.get("document_result")
    if isinstance(document_result, DocumentSearchResult):
        builder.add_query(document_result.query)
        builder.add_search_trace(
            "document_search",
            hit_count=len(document_result.hits),
            status=document_result.status.value,
        )
    for paragraph in paragraphs:
        page = _first_page_number(paragraph.pages)
        if page is None:
            continue
        builder.add_document(
            source_ref=paragraph.source,
            chunk_id=paragraph.chunk_id or paragraph.parent_header,
            paragraph_ref=paragraph.paragraph_ref,
            text=paragraph.text,
            page=page,
            image_refs=paragraph.image_refs,
        )
    web_result = state.get("web_result")
    if isinstance(web_result, WebSearchResult):
        builder.add_query(web_result.query)
        builder.add_search_trace(
            "web_search",
            hit_count=len(web_result.items),
            status=web_result.status,
        )
        for item in web_result.items:
            builder.add_web(
                title=item.title,
                url=item.url,
                snippet=item.snippet,
                content=item.content,
                retrieved_at=item.retrieved_at,
            )
    return builder.build()


def _first_page_number(pages: Sequence[str]) -> int | None:
    for page in pages:
        match = re.fullmatch(r"\s*(\d+)\s*", str(page))
        if match:
            value = int(match.group(1))
            if value > 0:
                return value
    return None


def _has_web_evidence(value: object) -> bool:
    if value is None:
        return False
    for name in ("items", "results", "hits", "evidence"):
        items = getattr(value, name, None)
        if items is not None:
            try:
                return len(items) > 0
            except TypeError:
                return bool(items)
    return True


def _reason_for_decision(decision: AgentDecision) -> str:
    return {
        AgentDecision.SELECT: "local_evidence_available",
        AgentDecision.WEB: "local_evidence_insufficient",
        AgentDecision.CLARIFY: "ambiguous_interpretation",
        AgentDecision.INSUFFICIENT: "no_evidence_available",
    }.get(decision, decision.value)


def _safe_error(error: BaseException) -> str:
    message = str(error).strip()
    return message or error.__class__.__name__


__all__ = [
    "AgentGraphDependencies",
    "GraphDependencyError",
    "build_agent_graph",
]
