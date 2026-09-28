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
from .evidence_selection import (
    ConceptRoleSelector,
    ParagraphDirectSelector,
    SelectionRequest,
    SelectionResult,
    adapt_legacy_selector,
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
    "SelectionRequest",
    "SelectionResult",
    "ParagraphDirectSelector",
    "ConceptRoleSelector",
    "adapt_legacy_selector",
    "AgentTool",
    "AnswerSynthesizer",
    "DocumentSearchTool",
    "EvidenceSelector",
    "WebSearchTool",
    "require_agent_tool",
]
