"""Validated contracts for one structured tagging call per source chunk."""

from __future__ import annotations

from dataclasses import dataclass

from .models import ContentRole, ParagraphBlock, _require_non_blank


_LABEL_ACTIONS = frozenset({"reuse_existing", "reuse_chunk_new", "create_new"})


@dataclass(frozen=True, slots=True)
class ChunkParagraphTaggingInput:
    """One source paragraph plus the candidate concepts available to its call."""

    paragraph: ParagraphBlock
    existing_candidates: tuple[str, ...] = ()
    previous_context: str = ""
    next_context: str = ""
    image_context: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.paragraph, ParagraphBlock):
            raise ValueError("paragraph must be a ParagraphBlock")
        _validate_concepts(self.existing_candidates, "existing_candidates")
        _validate_context(self.previous_context, "previous_context")
        _validate_context(self.next_context, "next_context")
        _validate_concepts(self.image_context, "image_context")
        object.__setattr__(self, "existing_candidates", tuple(item.strip() for item in self.existing_candidates))
        object.__setattr__(self, "image_context", tuple(item.strip() for item in self.image_context))


@dataclass(frozen=True, slots=True)
class ChunkTaggingRequest:
    """Source-preserving input for exactly one chunk-level tagging call."""

    chunk_id: str
    paragraphs: tuple[ChunkParagraphTaggingInput, ...]

    def __post_init__(self) -> None:
        _require_non_blank("chunk_id", self.chunk_id)
        if not self.paragraphs:
            raise ValueError("paragraphs must not be empty")
        if any(not isinstance(item, ChunkParagraphTaggingInput) for item in self.paragraphs):
            raise ValueError("paragraphs must contain ChunkParagraphTaggingInput values")
        refs = tuple(item.paragraph.paragraph_id for item in self.paragraphs)
        if len(set(refs)) != len(refs):
            raise ValueError("paragraphs must not contain duplicate paragraph refs")
        if any(item.paragraph.chunk_id != self.chunk_id.strip() for item in self.paragraphs):
            raise ValueError("every paragraph must belong to chunk_id")
        object.__setattr__(self, "chunk_id", self.chunk_id.strip())
        object.__setattr__(self, "paragraphs", tuple(self.paragraphs))


@dataclass(frozen=True, slots=True)
class ChunkTaggingLabel:
    """A concept resolution and its roles, kept together for one paragraph."""

    generated_concept: str
    action: str
    resolved_concept: str
    roles: tuple[ContentRole, ...]

    def __post_init__(self) -> None:
        _require_non_blank("generated_concept", self.generated_concept)
        _require_non_blank("resolved_concept", self.resolved_concept)
        if self.action not in _LABEL_ACTIONS:
            raise ValueError("action must be reuse_existing, reuse_chunk_new, or create_new")
        if not self.roles:
            raise ValueError("roles must contain at least one content role")
        try:
            roles = tuple(role if isinstance(role, ContentRole) else ContentRole(role) for role in self.roles)
        except (TypeError, ValueError) as exc:
            raise ValueError("roles must contain supported content roles") from exc
        if len(set(roles)) != len(roles):
            raise ValueError("roles must not contain duplicates")
        object.__setattr__(self, "generated_concept", self.generated_concept.strip())
        object.__setattr__(self, "resolved_concept", self.resolved_concept.strip())
        object.__setattr__(self, "roles", roles)


@dataclass(frozen=True, slots=True)
class ChunkParagraphTaggingResult:
    """The complete label set returned for one requested paragraph reference."""

    paragraph_ref: str
    labels: tuple[ChunkTaggingLabel, ...]
    tagging_status: str = "completed"

    def __post_init__(self) -> None:
        _require_non_blank("paragraph_ref", self.paragraph_ref)
        if self.tagging_status != "completed":
            raise ValueError("tagging_status must be completed")
        if any(not isinstance(label, ChunkTaggingLabel) for label in self.labels):
            raise ValueError("labels must contain ChunkTaggingLabel values")
        generated = tuple(label.generated_concept for label in self.labels)
        if len(set(generated)) != len(generated):
            raise ValueError("labels must not contain duplicate generated concepts")
        object.__setattr__(self, "paragraph_ref", self.paragraph_ref.strip())
        object.__setattr__(self, "labels", tuple(self.labels))


@dataclass(frozen=True, slots=True)
class ChunkTaggingResult:
    """A structured model output which must be reference-validated before commit."""

    chunk_id: str
    chunk_new_concepts: tuple[str, ...]
    paragraphs: tuple[ChunkParagraphTaggingResult, ...]

    def __post_init__(self) -> None:
        _require_non_blank("chunk_id", self.chunk_id)
        _validate_concepts(self.chunk_new_concepts, "chunk_new_concepts")
        if any(not isinstance(item, ChunkParagraphTaggingResult) for item in self.paragraphs):
            raise ValueError("paragraphs must contain ChunkParagraphTaggingResult values")
        refs = tuple(item.paragraph_ref for item in self.paragraphs)
        if len(set(refs)) != len(refs):
            raise ValueError("paragraphs must not contain duplicate paragraph refs")
        object.__setattr__(self, "chunk_id", self.chunk_id.strip())
        object.__setattr__(self, "chunk_new_concepts", tuple(item.strip() for item in self.chunk_new_concepts))
        object.__setattr__(self, "paragraphs", tuple(self.paragraphs))

    def validate_against(self, request: ChunkTaggingRequest) -> None:
        """Reject foreign refs and invalid concept provenance before persistence."""
        if not isinstance(request, ChunkTaggingRequest):
            raise ValueError("request must be a ChunkTaggingRequest")
        if self.chunk_id != request.chunk_id:
            raise ValueError("result chunk_id does not match request")
        requested = {item.paragraph.paragraph_id: item for item in request.paragraphs}
        returned_refs = {item.paragraph_ref for item in self.paragraphs}
        if returned_refs != set(requested):
            raise ValueError("result paragraph refs must exactly match request paragraph refs")
        new_concepts = set(self.chunk_new_concepts)
        for paragraph in self.paragraphs:
            candidates = set(requested[paragraph.paragraph_ref].existing_candidates)
            for label in paragraph.labels:
                if label.action == "reuse_existing" and label.resolved_concept not in candidates:
                    raise ValueError("reuse_existing requires an exact existing candidate")
                if label.action in {"reuse_chunk_new", "create_new"} and label.resolved_concept not in new_concepts:
                    raise ValueError(f"{label.action} requires resolved_concept in chunk_new_concepts")


def _validate_concepts(values: tuple[str, ...], field_name: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{field_name} must contain non-blank strings")
    normalized = tuple(value.strip() for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")


def _validate_context(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
