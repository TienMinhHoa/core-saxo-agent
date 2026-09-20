"""Composition helpers for the blocking Chroma infrastructure adapter."""

from __future__ import annotations

from typing import Any

from saxophone.app.settings import AppSettings
from saxophone.ingestion.adapters import ChromaVectorIndex


def create_chroma_vector_index(
    settings: AppSettings,
    *,
    io_limiter: Any | None = None,
) -> ChromaVectorIndex:
    """Create the configured persistent collection behind the application port."""
    import chromadb

    client = chromadb.PersistentClient(path=str(settings.chroma_persist_directory))
    collection = client.get_or_create_collection(name=settings.chroma_collection_name)
    return ChromaVectorIndex(collection, io_limiter=io_limiter)
