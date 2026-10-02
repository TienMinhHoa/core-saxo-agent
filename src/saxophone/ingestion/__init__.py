"""Public application facade for document ingestion and indexing."""

from importlib import import_module

_EXPORTS = {
    "build_source_chunks": (".chunking", "build_source_chunks"),
    "ChunkIndexRecord": (".models", "ChunkIndexRecord"),
    "IndexInputRecord": (".models", "IndexInputRecord"),
    "IngestionCommand": (".models", "IngestionCommand"),
    "IngestionReport": (".models", "IngestionReport"),
    "IngestionSourceChunk": (".models", "IngestionSourceChunk"),
    "EmbeddingProvider": (".ports", "EmbeddingProvider"),
    "EmbeddingReuseStore": (".ports", "EmbeddingReuseStore"),
    "VectorIndex": (".ports", "VectorIndex"),
    "DocumentState": (".state", "DocumentState"),
    "IngestionRunState": (".state", "IngestionRunState"),
    "IngestionStatus": (".state", "IngestionStatus"),
    "SqliteIngestionStateRepository": (".state", "SqliteIngestionStateRepository"),
    "DocumentChunkTaggingService": (
        ".use_cases",
        "DocumentChunkTaggingService",
    ),
    "IndexDocument": (".use_cases", "IndexDocument"),
    "IngestDocument": (".use_cases", "IngestDocument"),
    "DocumentIngestionService": (".services", "DocumentIngestionService"),
}

# Keep wildcard imports limited to provider-independent ingestion contracts.
# Use-case implementations remain available through explicit lazy imports.
_ACTIVE_EXPORTS = (
    "ChunkIndexRecord",
    "EmbeddingProvider",
    "EmbeddingReuseStore",
    "IndexInputRecord",
    "IngestionCommand",
    "IngestionReport",
    "IngestionSourceChunk",
    "VectorIndex",
    "build_source_chunks",
)

__all__ = list(_ACTIVE_EXPORTS)


def __getattr__(name: str) -> object:
    """Load facade exports only when a caller requests them."""

    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value
