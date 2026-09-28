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
    "AgentTool",
    "AnswerSynthesizer",
    "DocumentSearchTool",
    "EvidenceSelector",
    "WebSearchTool",
    "require_agent_tool",
]
