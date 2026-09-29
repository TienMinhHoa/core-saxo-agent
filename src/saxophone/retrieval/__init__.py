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

if TYPE_CHECKING:
    from .question_retrieval import (
        QuestionRequest,
        QuestionRetrievalService,
        RetrievalBundle,
        RetrievalBundleStatus,
    )
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


_COMPATIBILITY_EXPORTS = frozenset(
    {
        "QuestionRequest",
        "QuestionRetrievalService",
        "RetrievalBundle",
        "RetrievalBundleStatus",
    }
)

_LAZY_EXPORT_MODULES = {
    "ConceptRoleCandidate": ".role_selection",
    "ConceptRoleSelection": ".role_selection",
    "ConceptRoleSelectionRequest": ".role_selection",
    "ConceptRoleSelectionResult": ".role_selection",
    "ConceptRoleSelector": ".role_selection",
    "RemoteConceptRoleSelector": ".role_selection",
    "ConceptInventory": ".renderers",
    "ConceptInventoryBuilder": ".renderers",
    "ParagraphTraversal": ".paragraph_traversal",
    "ParagraphChoice": ".paragraph_selection",
    "ParagraphSelection": ".paragraph_selection",
    "ParagraphSelectionRequest": ".paragraph_selection",
    "ParagraphSelectionResult": ".paragraph_selection",
    "StructuredParagraphSelector": ".paragraph_selection",
    "build_paragraph_choices": ".paragraph_selection",
    "render_paragraph_choices": ".paragraph_selection",
    "ContextLimiter": ".context_limiter",
}


def __getattr__(name: str) -> object:
    """Resolve compatibility and optional selector APIs only when requested."""

    if name in _COMPATIBILITY_EXPORTS:
        module = import_module(".question_retrieval", __name__)
        return getattr(module, name)
    module_name = _LAZY_EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    module = import_module(module_name, __name__)
    return getattr(module, name)

__all__ = [
    "ChunkHit",
    "ChunkRetriever",
    "EvidenceBundle",
    "RetrieveEvidence",
]
