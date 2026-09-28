"""Domain contracts for the multi-agent orchestration boundary."""

from .contracts import (
    AgentOutcome,
    AgentQuestion,
    Citation,
    ClarificationRequest,
    EvidenceItem,
    EvidenceLedger,
    EvidenceSourceType,
    SearchTrace,
    SelectionStrategy,
)
from .document_search import (
    DocumentSearchResult,
    DocumentSearchService,
    DocumentSearchStatus,
    DocumentSearchToolAdapter,
    SemanticDocumentSearchTool,
)
from .ports import (
    AgentTool,
    AnswerSynthesizer,
    DocumentSearchTool,
    EvidenceSelector,
    WebSearchTool,
    require_agent_tool,
)

__all__ = [
    "AgentOutcome",
    "AgentQuestion",
    "Citation",
    "ClarificationRequest",
    "EvidenceItem",
    "EvidenceLedger",
    "EvidenceSourceType",
    "SearchTrace",
    "SelectionStrategy",
    "DocumentSearchResult",
    "DocumentSearchService",
    "DocumentSearchStatus",
    "DocumentSearchToolAdapter",
    "SemanticDocumentSearchTool",
    "AgentTool",
    "AnswerSynthesizer",
    "DocumentSearchTool",
    "EvidenceSelector",
    "WebSearchTool",
    "require_agent_tool",
]
