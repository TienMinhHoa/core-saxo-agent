"""Public retrieval facade for application consumers."""

from .models import ChunkHit, EvidenceBundle
from .ports import ChunkRetriever
from .use_cases import RetrieveEvidence

__all__ = [
    "ChunkHit",
    "ChunkRetriever",
    "EvidenceBundle",
    "RetrieveEvidence",
]
