"""Domain contracts for the multi-agent orchestration boundary."""

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
from .document_search import (
    DocumentSearchResult,
    DocumentSearchService,
    DocumentSearchStatus,
    DocumentSearchToolAdapter,
    SemanticDocumentSearchTool,
)
from .evidence_selection import (
    ConceptRoleSelector,
    ParagraphDirectSelector,
    SelectionRequest,
    SelectionResult,
)
from .evidence import EvidenceLedgerBuilder, stable_evidence_id
from .ports import (
    AgentTool,
    AnswerSynthesizer,
    DocumentSearchTool,
    EvidenceSelector,
    WebSearchTool,
    require_agent_tool,
)
from .graph import AgentGraphDependencies, GraphDependencyError, build_agent_graph
from .orchestrator import AgentRunResult, MainAgent
from .state import AgentDecision, AgentGraphState, AgentStage, GraphStage, GraphState
from .policies import (
    BudgetDecision,
    BudgetPolicy,
    BudgetTimeoutError,
    ClarificationPolicy,
    call_with_budget,
    check_budget,
    enforce_budget,
    execute_with_budget,
    run_with_budget,
)
from .synthesis import EvidenceSynthesisService, SynthesisCitation, SynthesisOutput
from .langchain_tools import (
    AgentToolInput,
    DocumentSearchLangChainTool,
    WebSearchLangChainTool,
    create_document_search_tool,
    create_web_search_tool,
)
from .web_search import (
    WebSearchAdapter,
    WebSearchProvider,
    WebSearchService,
    WebSearchToolAdapter,
)
from .events import AgentEvent, AgentEventSink, AgentEventType
from .langchain_callbacks import AgentEventCallbackHandler, AgentTracingCallbackHandler
from .streaming import AgentRunManager
from .tracing import (
    AgentTracer,
    InMemoryTracer,
    NoopTracer,
    ObservationKind,
    TraceContext,
    TraceObservation,
    TraceRecord,
    TraceStatus,
    redact_payload,
)

_COMPATIBILITY_EXPORTS = frozenset({"adapt_legacy_selector"})


def __getattr__(name: str) -> object:
    """Resolve migration-only helpers without loading them for active agents."""

    if name not in _COMPATIBILITY_EXPORTS:
        raise AttributeError(name)
    from saxophone.retrieval.selector_compatibility import adapt_legacy_selector

    return adapt_legacy_selector

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
    "DocumentSearchResult",
    "DocumentSearchService",
    "DocumentSearchStatus",
    "DocumentSearchToolAdapter",
    "SemanticDocumentSearchTool",
    "SelectionRequest",
    "SelectionResult",
    "ParagraphDirectSelector",
    "ConceptRoleSelector",
    "adapt_legacy_selector",
    "EvidenceLedgerBuilder",
    "stable_evidence_id",
    "AgentTool",
    "AnswerSynthesizer",
    "DocumentSearchTool",
    "EvidenceSelector",
    "WebSearchTool",
    "require_agent_tool",
    "BudgetDecision",
    "BudgetPolicy",
    "BudgetTimeoutError",
    "ClarificationPolicy",
    "call_with_budget",
    "check_budget",
    "enforce_budget",
    "execute_with_budget",
    "run_with_budget",
    "AgentDecision",
    "AgentGraphDependencies",
    "AgentGraphState",
    "AgentRunResult",
    "AgentStage",
    "GraphStage",
    "GraphDependencyError",
    "GraphState",
    "MainAgent",
    "build_agent_graph",
    "EvidenceSynthesisService",
    "SynthesisCitation",
    "SynthesisOutput",
    "AgentToolInput",
    "DocumentSearchLangChainTool",
    "WebSearchLangChainTool",
    "create_document_search_tool",
    "create_web_search_tool",
    "WebSearchAdapter",
    "WebSearchProvider",
    "WebSearchService",
    "WebSearchToolAdapter",
    "AgentEvent",
    "AgentEventSink",
    "AgentEventType",
    "AgentEventCallbackHandler",
    "AgentTracingCallbackHandler",
    "AgentRunManager",
    "AgentTracer",
    "InMemoryTracer",
    "NoopTracer",
    "ObservationKind",
    "TraceContext",
    "TraceObservation",
    "TraceRecord",
    "TraceStatus",
    "redact_payload",
]
