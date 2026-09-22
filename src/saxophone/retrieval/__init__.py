"""Public retrieval facade for application consumers."""

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
from .context_limiter import ContextLimiter
from .question_retrieval import QuestionRequest, QuestionRetrievalService, RetrievalBundle, RetrievalBundleStatus

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
    "ContextLimiter",
    "QuestionRequest",
    "QuestionRetrievalService",
    "RetrievalBundle",
    "RetrievalBundleStatus",
]
