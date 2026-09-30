"""Public facade for the multi-agent orchestration boundary.

Contract imports stay lightweight. Graph, adapter, and compatibility
implementations are resolved only when a consumer requests an explicit
attribute, keeping ordinary application imports free of optional runtimes.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .contracts import (
        AgentOutcome,
        AgentQuestion,
        BudgetCall,
        BudgetExhaustedError,
        BudgetSnapshot,
        Citation,
        ClarificationCandidate,
        ClarificationRequest,
        EvidenceItem,
        EvidenceLedger,
        EvidenceSourceType,
        InterpretationCandidate,
        RunBudget,
        SearchTrace,
        SelectionStrategy,
        SynthesisResult,
        WebSearchItem,
        WebSearchResult,
    )


_EXPORTS: dict[str, tuple[str, str]] = {
    "AgentOutcome": (".contracts", "AgentOutcome"),
    "AgentQuestion": (".contracts", "AgentQuestion"),
    "BudgetCall": (".contracts", "BudgetCall"),
    "BudgetExhaustedError": (".contracts", "BudgetExhaustedError"),
    "BudgetSnapshot": (".contracts", "BudgetSnapshot"),
    "Citation": (".contracts", "Citation"),
    "ClarificationCandidate": (".contracts", "ClarificationCandidate"),
    "ClarificationRequest": (".contracts", "ClarificationRequest"),
    "EvidenceItem": (".contracts", "EvidenceItem"),
    "EvidenceLedger": (".contracts", "EvidenceLedger"),
    "EvidenceSourceType": (".contracts", "EvidenceSourceType"),
    "InterpretationCandidate": (".contracts", "InterpretationCandidate"),
    "RunBudget": (".contracts", "RunBudget"),
    "SearchTrace": (".contracts", "SearchTrace"),
    "SelectionStrategy": (".contracts", "SelectionStrategy"),
    "SynthesisResult": (".contracts", "SynthesisResult"),
    "WebSearchItem": (".contracts", "WebSearchItem"),
    "WebSearchResult": (".contracts", "WebSearchResult"),
    "DocumentSearchResult": (".document_search", "DocumentSearchResult"),
    "DocumentSearchService": (".document_search", "DocumentSearchService"),
    "DocumentSearchStatus": (".document_search", "DocumentSearchStatus"),
    "DocumentSearchToolAdapter": (".document_search", "DocumentSearchToolAdapter"),
    "SemanticDocumentSearchTool": (".document_search", "SemanticDocumentSearchTool"),
    "ConceptRoleSelector": (".evidence_selection", "ConceptRoleSelector"),
    "ParagraphDirectSelector": (".evidence_selection", "ParagraphDirectSelector"),
    "SelectionRequest": (".evidence_selection", "SelectionRequest"),
    "SelectionResult": (".evidence_selection", "SelectionResult"),
    "EvidenceLedgerBuilder": (".evidence", "EvidenceLedgerBuilder"),
    "stable_evidence_id": (".evidence", "stable_evidence_id"),
    "AgentTool": (".ports", "AgentTool"),
    "AnswerSynthesizer": (".ports", "AnswerSynthesizer"),
    "DocumentSearchTool": (".ports", "DocumentSearchTool"),
    "EvidenceSelector": (".ports", "EvidenceSelector"),
    "WebSearchTool": (".ports", "WebSearchTool"),
    "require_agent_tool": (".ports", "require_agent_tool"),
    "AgentGraphDependencies": (".graph", "AgentGraphDependencies"),
    "GraphDependencyError": (".graph", "GraphDependencyError"),
    "build_agent_graph": (".graph", "build_agent_graph"),
    "AgentRunResult": (".orchestrator", "AgentRunResult"),
    "MainAgent": (".orchestrator", "MainAgent"),
    "AgentDecision": (".state", "AgentDecision"),
    "AgentGraphState": (".state", "AgentGraphState"),
    "AgentStage": (".state", "AgentStage"),
    "GraphStage": (".state", "GraphStage"),
    "GraphState": (".state", "GraphState"),
    "BudgetDecision": (".policies", "BudgetDecision"),
    "BudgetPolicy": (".policies", "BudgetPolicy"),
    "BudgetTimeoutError": (".policies", "BudgetTimeoutError"),
    "ClarificationPolicy": (".policies", "ClarificationPolicy"),
    "call_with_budget": (".policies", "call_with_budget"),
    "check_budget": (".policies", "check_budget"),
    "enforce_budget": (".policies", "enforce_budget"),
    "execute_with_budget": (".policies", "execute_with_budget"),
    "run_with_budget": (".policies", "run_with_budget"),
    "EvidenceSynthesisService": (".synthesis", "EvidenceSynthesisService"),
    "SynthesisCitation": (".synthesis", "SynthesisCitation"),
    "SynthesisOutput": (".synthesis", "SynthesisOutput"),
    "AgentToolInput": (".langchain_tools", "AgentToolInput"),
    "DocumentSearchLangChainTool": (".langchain_tools", "DocumentSearchLangChainTool"),
    "WebSearchLangChainTool": (".langchain_tools", "WebSearchLangChainTool"),
    "create_document_search_tool": (".langchain_tools", "create_document_search_tool"),
    "create_web_search_tool": (".langchain_tools", "create_web_search_tool"),
    "WebSearchAdapter": (".web_search", "WebSearchAdapter"),
    "WebSearchProvider": (".web_search", "WebSearchProvider"),
    "WebSearchService": (".web_search", "WebSearchService"),
    "WebSearchToolAdapter": (".web_search", "WebSearchToolAdapter"),
    "AgentEvent": (".events", "AgentEvent"),
    "AgentEventSink": (".events", "AgentEventSink"),
    "AgentEventType": (".events", "AgentEventType"),
    "AgentEventCallbackHandler": (".langchain_callbacks", "AgentEventCallbackHandler"),
    "AgentTracingCallbackHandler": (".langchain_callbacks", "AgentTracingCallbackHandler"),
    "AgentRunManager": (".streaming", "AgentRunManager"),
    "AgentTracer": (".tracing", "AgentTracer"),
    "InMemoryTracer": (".tracing", "InMemoryTracer"),
    "NoopTracer": (".tracing", "NoopTracer"),
    "ObservationKind": (".tracing", "ObservationKind"),
    "TraceContext": (".tracing", "TraceContext"),
    "TraceObservation": (".tracing", "TraceObservation"),
    "TraceRecord": (".tracing", "TraceRecord"),
    "TraceStatus": (".tracing", "TraceStatus"),
    "redact_payload": (".tracing", "redact_payload"),
}

_COMPATIBILITY_EXPORTS = frozenset({"adapt_legacy_selector"})

# Wildcard imports expose only the stable contract facade. Explicit imports of
# implementation symbols remain supported through __getattr__ below.
__all__ = [
    "AgentOutcome",
    "AgentQuestion",
    "BudgetCall",
    "BudgetExhaustedError",
    "BudgetSnapshot",
    "Citation",
    "ClarificationCandidate",
    "ClarificationRequest",
    "EvidenceItem",
    "EvidenceLedger",
    "EvidenceSourceType",
    "InterpretationCandidate",
    "RunBudget",
    "SearchTrace",
    "SelectionStrategy",
    "SynthesisResult",
    "WebSearchItem",
    "WebSearchResult",
]


def __getattr__(name: str) -> Any:
    """Resolve public symbols only when a consumer requests them."""

    if name in _COMPATIBILITY_EXPORTS:
        from saxophone.retrieval.selector_compatibility import adapt_legacy_selector

        return adapt_legacy_selector
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value
