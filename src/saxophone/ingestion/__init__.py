"""Public application facade for document ingestion and indexing."""

from .chunking import build_source_chunks
from .models import (
    ChunkIndexRecord,
    IndexInputRecord,
    IngestionCommand,
    IngestionReport,
    IngestionSourceChunk,
)
from .ports import EmbeddingProvider, VectorIndex

__all__ = [
    "ChunkIndexRecord",
    "EmbeddingProvider",
    "IndexDocument",
    "IndexInputRecord",
    "IngestionCommand",
    "IngestionReport",
    "IngestionSourceChunk",
    "VectorIndex",
    "build_source_chunks",
]


def __getattr__(name: str) -> object:
    """Load the use case lazily to avoid a domain-port import cycle."""

    if name == "IndexDocument":
        from .use_cases import IndexDocument

        return IndexDocument
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
