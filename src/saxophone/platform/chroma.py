"""Composition helpers for the blocking Chroma infrastructure adapter."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from typing import Any, Protocol

from saxophone.ingestion.adapters import ChromaVectorIndex


_CHROMA_SCHEMA_VERSION = "saxo-chunk-v1"


class ChromaSettings(Protocol):
    """Configuration shape required by the Chroma infrastructure adapter."""

    chroma_persist_directory: Any
    chroma_collection_name: str
    chroma_concept_collection_name: str
    embedding_dimension: int


def create_chroma_vector_index(
    settings: ChromaSettings,
    *,
    io_limiter: Any | None = None,
) -> ChromaVectorIndex:
    """Create the configured persistent collection behind the application port."""
    import chromadb

    client = chromadb.PersistentClient(path=str(settings.chroma_persist_directory))
    try:
        metadata = {
            "embedding_dimension": settings.embedding_dimension,
            "schema_version": _CHROMA_SCHEMA_VERSION,
        }
        collection = client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata=metadata,
        )
        _validate_collection_metadata(collection, settings)
        concept_collection = client.get_or_create_collection(
            name=settings.chroma_concept_collection_name,
            metadata=metadata,
        )
        _validate_collection_metadata(concept_collection, settings)
        return ChromaVectorIndex(
            collection,
            client=client,
            concept_collection=concept_collection,
            io_limiter=io_limiter,
            embedding_dimension=settings.embedding_dimension,
        )
    except BaseException:
        close = getattr(client, "close", None)
        if callable(close):
            with suppress(Exception):
                close()
        raise


def _validate_collection_metadata(collection: Any, settings: ChromaSettings) -> None:
    metadata = getattr(collection, "metadata", None)
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ValueError("Chroma collection metadata must be a mapping")
    metadata = metadata or {}
    stored_dimension = metadata.get("embedding_dimension")
    if stored_dimension is not None and (
        type(stored_dimension) is not int or stored_dimension <= 0
    ):
        raise ValueError("Chroma collection embedding dimension metadata is invalid")
    if stored_dimension is not None and stored_dimension != settings.embedding_dimension:
        raise ValueError(
            "Chroma collection embedding dimension does not match configured embedding dimension"
        )
    stored_schema_version = metadata.get("schema_version")
    # Collections created before schema metadata was introduced remain usable;
    # an explicitly different version is the unsafe case and must fail closed.
    if stored_schema_version is not None and (
        type(stored_schema_version) is not str or not stored_schema_version.strip()
    ):
        raise ValueError("Chroma collection schema version metadata is invalid")
    if stored_schema_version is not None and stored_schema_version != _CHROMA_SCHEMA_VERSION:
        raise ValueError(
            "Chroma collection schema version does not match configured schema version"
        )
