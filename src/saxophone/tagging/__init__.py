"""Public application facade for paragraph tagging.

The facade keeps provider, persistence, and parsing implementations behind
explicit attribute access. Importing the package alone therefore stays
lightweight while existing public imports remain available.
"""

from importlib import import_module

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

# Keep wildcard imports limited to provider-independent tagging contracts.
# Adapter, persistence, parser, and use-case implementations remain available
# through explicit lazy attribute access below.
_ACTIVE_EXPORTS = (
    "ExistingTagCandidate",
    "ParagraphBlock",
    "ParagraphConceptRole",
    "TagConflictResolution",
    "TagConflictResolutionRequest",
    "TagGenerationRequest",
    "TagGenerationResult",
    "TagResolution",
    "TaggedParagraph",
    "ConceptCandidate",
    "ConceptCandidateExample",
    "deduplicate_concept_candidates",
    "normalize_concept_label",
    "ChunkTagger",
    "TagCatalogRepository",
    "TagConflictResolver",
    "TagGenerator",
    "TaggedParagraphRepository",
)

__all__ = list(_ACTIVE_EXPORTS)


def __getattr__(name: str) -> object:
    """Resolve facade exports only when a consumer asks for them."""

    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value
