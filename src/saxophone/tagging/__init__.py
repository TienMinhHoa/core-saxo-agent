"""Public application facade for paragraph tagging."""

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
    TagConflictResolution,
    TagConflictResolutionRequest,
    TagGenerationRequest,
    TagGenerationResult,
    TagResolution,
    TaggedParagraph,
)
from .persistence import JsonTagCatalogRepository, JsonTaggedParagraphRepository
from .ports import (
    TagCatalogRepository,
    TagConflictResolver,
    TagGenerator,
    TaggedParagraphRepository,
)

__all__ = [
    "ExistingTagCandidate",
    "ConceptCandidate",
    "ConceptCandidateExample",
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
    "deduplicate_concept_candidates",
    "normalize_concept_label",
    "parse_chunk_paragraphs",
]


def __getattr__(name: str) -> object:
    """Load workflow/parser exports lazily to avoid ingestion import cycles."""

    if name in {"TagAndPersistParagraph", "TagParagraph"}:
        from .use_cases import TagAndPersistParagraph, TagParagraph

        return {"TagAndPersistParagraph": TagAndPersistParagraph, "TagParagraph": TagParagraph}[name]
    if name == "parse_chunk_paragraphs":
        from .parser import parse_chunk_paragraphs

        return parse_chunk_paragraphs
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
