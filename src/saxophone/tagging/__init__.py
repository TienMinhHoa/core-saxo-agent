"""Public application facade for paragraph tagging.

The facade keeps provider, persistence, and parsing implementations behind
explicit attribute access. Importing the package alone therefore stays
lightweight while existing public imports remain available.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .adapters import RemoteParagraphTagger, RemoteTagConflictResolver
    from .concepts import (
        ConceptCandidate,
        ConceptCandidateExample,
        deduplicate_concept_candidates,
        normalize_concept_label,
    )
    from .models import (
        ExistingTagCandidate,
        ParagraphBlock,
        ParagraphConceptRole,
        TagConflictResolution,
        TagConflictResolutionRequest,
        TagGenerationRequest,
        TagGenerationResult,
        TagResolution,
        TaggedParagraph,
    )
    from .persistence import JsonTagCatalogRepository, JsonTaggedParagraphRepository
    from .ports import (
        ChunkTagger,
        TagCatalogRepository,
        TagConflictResolver,
        TagGenerator,
        TaggedParagraphRepository,
    )
    from .use_cases import TagAndPersistParagraph, TagParagraph
    from .parser import parse_chunk_paragraphs


_EXPORTS: dict[str, tuple[str, str]] = {
    "RemoteParagraphTagger": (".adapters", "RemoteParagraphTagger"),
    "RemoteTagConflictResolver": (".adapters", "RemoteTagConflictResolver"),
    "ConceptCandidate": (".concepts", "ConceptCandidate"),
    "ConceptCandidateExample": (".concepts", "ConceptCandidateExample"),
    "deduplicate_concept_candidates": (".concepts", "deduplicate_concept_candidates"),
    "normalize_concept_label": (".concepts", "normalize_concept_label"),
    "ExistingTagCandidate": (".models", "ExistingTagCandidate"),
    "ParagraphBlock": (".models", "ParagraphBlock"),
    "ParagraphConceptRole": (".models", "ParagraphConceptRole"),
    "TagConflictResolution": (".models", "TagConflictResolution"),
    "TagConflictResolutionRequest": (".models", "TagConflictResolutionRequest"),
    "TagGenerationRequest": (".models", "TagGenerationRequest"),
    "TagGenerationResult": (".models", "TagGenerationResult"),
    "TagResolution": (".models", "TagResolution"),
    "TaggedParagraph": (".models", "TaggedParagraph"),
    "JsonTagCatalogRepository": (".persistence", "JsonTagCatalogRepository"),
    "JsonTaggedParagraphRepository": (".persistence", "JsonTaggedParagraphRepository"),
    "ChunkTagger": (".ports", "ChunkTagger"),
    "TagCatalogRepository": (".ports", "TagCatalogRepository"),
    "TagConflictResolver": (".ports", "TagConflictResolver"),
    "TagGenerator": (".ports", "TagGenerator"),
    "TaggedParagraphRepository": (".ports", "TaggedParagraphRepository"),
    "TagAndPersistParagraph": (".use_cases", "TagAndPersistParagraph"),
    "TagParagraph": (".use_cases", "TagParagraph"),
    "parse_chunk_paragraphs": (".parser", "parse_chunk_paragraphs"),
}

__all__ = [
    "ExistingTagCandidate",
    "JsonTagCatalogRepository",
    "JsonTaggedParagraphRepository",
    "ParagraphBlock",
    "RemoteParagraphTagger",
    "RemoteTagConflictResolver",
    "TagAndPersistParagraph",
    "TagCatalogRepository",
    "TagConflictResolution",
    "TagConflictResolutionRequest",
    "TagConflictResolver",
    "TagGenerationRequest",
    "TagGenerationResult",
    "TagGenerator",
    "TagParagraph",
    "TagResolution",
    "TaggedParagraph",
    "TaggedParagraphRepository",
    "parse_chunk_paragraphs",
]


def __getattr__(name: str) -> object:
    """Resolve facade exports only when a consumer asks for them."""

    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value
