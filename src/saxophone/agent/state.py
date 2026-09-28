"""Typed state exchanged by the compiled Main Agent graph."""

from __future__ import annotations

from enum import StrEnum
from typing import TypedDict

from .contracts import (
    AgentOutcome,
    AgentQuestion,
    ClarificationRequest,
    EvidenceLedger,
    RunBudget,
    SelectionStrategy,
    SynthesisResult,
    WebSearchResult,
)
from .document_search import DocumentSearchResult
from .evidence_selection import SelectionResult


class AgentStage(StrEnum):
    """Observable lifecycle stages for one graph invocation."""

    RECEIVED = "received"
    DOCUMENT_SEARCHING = "document_searching"
    SELECTING_EVIDENCE = "selecting_evidence"
    EVALUATING_EVIDENCE = "evaluating_evidence"
    WEB_SEARCHING = "web_searching"
    WAITING_FOR_CLARIFICATION = "waiting_for_clarification"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentDecision(StrEnum):
    """Internal graph routes kept separate from public run outcomes."""

    SELECT = "select"
    SYNTHESIZE = "synthesize"
    WEB = "web"
    CLARIFY = "clarify"
    INSUFFICIENT = "insufficient"
    VALIDATE = "validate"
    COMPLETE = "complete"
    FAILED = "failed"


class AgentGraphState(TypedDict, total=False):
    """State schema accepted by LangGraph nodes.

    The graph state contains orchestration data only.  Retrieval and synthesis
    adapters exchange the immutable domain DTOs from ``contracts`` instead of
    leaking provider dictionaries into the graph.
    """

    run_id: str
    question: AgentQuestion
    budget: RunBudget
    stage: AgentStage
    outcome: AgentOutcome
    decision: AgentDecision
    document_result: DocumentSearchResult
    web_result: WebSearchResult
    selection_strategy: SelectionStrategy
    selection_result: SelectionResult
    ledger: EvidenceLedger
    synthesis_result: SynthesisResult
    answer: str
    clarification: ClarificationRequest
    error: str
    reason_code: str


GraphState = AgentGraphState
GraphStage = AgentStage


def state_stage(state: AgentGraphState) -> AgentStage:
    """Return a normalized stage for callers inspecting graph output."""

    value = state.get("stage", AgentStage.FAILED)
    return value if isinstance(value, AgentStage) else AgentStage(value)


__all__ = [
    "AgentDecision",
    "AgentGraphState",
    "AgentStage",
    "GraphStage",
    "GraphState",
    "state_stage",
]
