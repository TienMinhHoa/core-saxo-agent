"""Composition helpers for the blocking Chroma infrastructure adapter."""

from __future__ import annotations

from typing import Any

from saxophone.app.settings import AppSettings
from saxophone.ingestion.adapters import ChromaVectorIndex


_CHROMA_SCHEMA_VERSION = "saxo-chunk-v1"


def create_chroma_vector_index(
    settings: AppSettings,
    *,
    io_limiter: Any | None = None,
) -> ChromaVectorIndex:
    """Create the configured persistent collection behind the application port."""
    import chromadb

    client = chromadb.PersistentClient(path=str(settings.chroma_persist_directory))
    collection = client.get_or_create_collection(
        name=settings.chroma_collection_name,
        metadata={
            "embedding_dimension": settings.embedding_dimension,
            "schema_version": _CHROMA_SCHEMA_VERSION,
        },
    )
    metadata = getattr(collection, "metadata", None) or {}
    stored_dimension = metadata.get("embedding_dimension")
    if stored_dimension is not None and stored_dimension != settings.embedding_dimension:
        raise ValueError(
            "Chroma collection embedding dimension does not match configured embedding dimension"
        )
    return ChromaVectorIndex(collection, io_limiter=io_limiter)
