"""Public retrieval facade for application consumers.

The question-retrieval service is a compatibility boundary for the pre-agent
chat flow.  Keep it out of the package's eager import path so agent modules can
use the active retrieval contracts without loading the legacy orchestration
stack as a side effect.
"""

from importlib import import_module
from typing import TYPE_CHECKING

from .models import ChunkHit, EvidenceBundle
from .ports import ChunkRetriever
from .use_cases import RetrieveEvidence
from .role_selection import (
    ConceptRoleCandidate,
    ConceptRoleSelection,
    ConceptRoleSelectionRequest,
    ConceptRoleSelectionResult,
    ConceptRoleSelector,
    RemoteConceptRoleSelector,
)
from .renderers import ConceptInventory, ConceptInventoryBuilder
from .paragraph_traversal import ParagraphTraversal
from .paragraph_selection import (
    ParagraphChoice,
    ParagraphSelection,
    ParagraphSelectionRequest,
    ParagraphSelectionResult,
    StructuredParagraphSelector,
    build_paragraph_choices,
    render_paragraph_choices,
)
from .context_limiter import ContextLimiter

if TYPE_CHECKING:
    from .question_retrieval import (
        QuestionRequest,
        QuestionRetrievalService,
        RetrievalBundle,
        RetrievalBundleStatus,
    )


_COMPATIBILITY_EXPORTS = frozenset(
    {
        "QuestionRequest",
        "QuestionRetrievalService",
        "RetrievalBundle",
        "RetrievalBundleStatus",
    }
)


def __getattr__(name: str) -> object:
    """Resolve compatibility retrieval exports only when a caller requests one."""

    if name not in _COMPATIBILITY_EXPORTS:
        raise AttributeError(name)
    compatibility = import_module(".question_retrieval", __name__)
    return getattr(compatibility, name)

__all__ = [
    "ChunkHit",
    "ChunkRetriever",
    "EvidenceBundle",
    "RetrieveEvidence",
    "ConceptRoleCandidate",
    "ConceptRoleSelection",
    "ConceptRoleSelectionRequest",
    "ConceptRoleSelectionResult",
    "ConceptRoleSelector",
    "RemoteConceptRoleSelector",
    "ConceptInventory",
    "ConceptInventoryBuilder",
    "ParagraphTraversal",
    "ParagraphChoice",
    "ParagraphSelection",
    "ParagraphSelectionRequest",
    "ParagraphSelectionResult",
    "StructuredParagraphSelector",
    "build_paragraph_choices",
    "render_paragraph_choices",
    "ContextLimiter",
    "QuestionRequest",
    "QuestionRetrievalService",
    "RetrievalBundle",
    "RetrievalBundleStatus",
]
