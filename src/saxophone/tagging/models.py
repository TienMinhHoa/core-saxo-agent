"""Immutable DTOs for paragraph-level topic tag generation."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ExistingTagCandidate:
    """An existing plain-English tag eligible for conflict resolution."""

    tag: str
    examples: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_blank("tag", self.tag)
        if any(not isinstance(example, str) or not example.strip() for example in self.examples):
            raise ValueError("examples must contain non-blank strings")
        object.__setattr__(self, "tag", self.tag.strip())
        object.__setattr__(self, "examples", tuple(self.examples))


@dataclass(frozen=True, slots=True)
class TagConflictResolutionRequest:
    """Input to the separate conflict-resolution model task."""

    paragraph_id: str
    generated_tags: tuple[str, ...]
    existing_tags: tuple[ExistingTagCandidate, ...]
    resolution_profile: str

    def __post_init__(self) -> None:
        _require_non_blank("paragraph_id", self.paragraph_id)
        _require_non_blank("resolution_profile", self.resolution_profile)
        _validate_tags(self.generated_tags, "generated_tags")
        if any(not isinstance(candidate, ExistingTagCandidate) for candidate in self.existing_tags):
            raise ValueError("existing_tags must contain ExistingTagCandidate values")
        if len({candidate.tag for candidate in self.existing_tags}) != len(self.existing_tags):
            raise ValueError("existing_tags must not contain duplicates")
        object.__setattr__(self, "generated_tags", tuple(tag.strip() for tag in self.generated_tags))
        object.__setattr__(self, "existing_tags", tuple(self.existing_tags))


@dataclass(frozen=True, slots=True)
class TagResolution:
    """One generated tag mapped to exactly one final action."""

    generated_tag: str
    action: str
    resolved_tag: str

    def __post_init__(self) -> None:
        _require_non_blank("generated_tag", self.generated_tag)
        _require_non_blank("resolved_tag", self.resolved_tag)
        if self.action not in {"reuse_existing", "keep_new"}:
            raise ValueError("action must be reuse_existing or keep_new")
        object.__setattr__(self, "generated_tag", self.generated_tag.strip())
        object.__setattr__(self, "resolved_tag", self.resolved_tag.strip())


@dataclass(frozen=True, slots=True)
class TagConflictResolution:
    """Validated output of conflict resolution with no silent fallback."""

    paragraph_id: str
    resolutions: tuple[TagResolution | tuple[str, str, str], ...]
    resolution_profile: str
    generated_tags: tuple[str, ...] = ()
    existing_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_blank("paragraph_id", self.paragraph_id)
        _require_non_blank("resolution_profile", self.resolution_profile)
        normalized = tuple(
            value if isinstance(value, TagResolution) else TagResolution(*value)
            for value in self.resolutions
        )
        generated = tuple(tag.strip() for tag in self.generated_tags)
        existing = tuple(tag.strip() for tag in self.existing_tags)
        if generated and len({item.generated_tag for item in normalized}) != len(normalized):
            raise ValueError("each generated tag must have exactly one resolution")
        if generated and set(generated) != {item.generated_tag for item in normalized}:
            raise ValueError("each generated tag must have exactly one resolution")
        candidates = set(existing)
        for item in normalized:
            if item.action == "reuse_existing" and item.resolved_tag not in candidates:
                if not candidates:
                    raise ValueError("empty candidate list only allows keep_new")
                raise ValueError("reuse_existing requires an existing tag candidate")
            if not candidates and item.action != "keep_new":
                raise ValueError("empty candidate list only allows keep_new")
        object.__setattr__(self, "resolutions", normalized)
        object.__setattr__(self, "generated_tags", generated)
        object.__setattr__(self, "existing_tags", existing)


@dataclass(frozen=True, slots=True)
class ParagraphBlock:
    """A source paragraph identified without changing its source text."""

    paragraph_id: str
    chunk_id: str
    ordinal: int
    text: str
    heading_path: tuple[str, ...] = ()
    image_refs: tuple[str, ...] = ()
    image_captions: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        for name in ("paragraph_id", "chunk_id", "text"):
            _require_non_blank(name, getattr(self, name))
        if self.ordinal < 0:
            raise ValueError("ordinal must not be negative")
        if any(not isinstance(value, str) or not value.strip() for value in self.heading_path):
            raise ValueError("heading_path must contain non-blank strings")
        if any(not isinstance(value, str) or not value.strip() for value in self.image_refs):
            raise ValueError("image_refs must contain non-blank strings")
        if len(set(self.image_refs)) != len(self.image_refs):
            raise ValueError("image_refs must not contain duplicates")
        if not isinstance(self.image_captions, Mapping):
            raise ValueError("image_captions must be a mapping")
        if any(ref not in self.image_refs for ref in self.image_captions):
            raise ValueError("image_captions must reference image_refs")
        if any(not isinstance(caption, str) or not caption.strip() for caption in self.image_captions.values()):
            raise ValueError("image_captions must contain non-blank strings")
        object.__setattr__(self, "heading_path", tuple(self.heading_path))
        object.__setattr__(self, "image_refs", tuple(self.image_refs))
        object.__setattr__(self, "image_captions", MappingProxyType(dict(self.image_captions)))


@dataclass(frozen=True, slots=True)
class TagGenerationRequest:
    """Input for a generation-only model task; existing tags stay separate."""

    paragraph: ParagraphBlock
    tagging_profile: str

    def __post_init__(self) -> None:
        _require_non_blank("tagging_profile", self.tagging_profile)


@dataclass(frozen=True, slots=True)
class TagGenerationResult:
    """Validated plain-English tags returned for one unchanged paragraph."""

    paragraph_id: str
    tags: tuple[str, ...]
    tagging_profile: str

    def __post_init__(self) -> None:
        _require_non_blank("paragraph_id", self.paragraph_id)
        _require_non_blank("tagging_profile", self.tagging_profile)
        if not isinstance(self.tags, tuple):
            raise ValueError("tags must be a tuple")
        if any(not isinstance(tag, str) or not tag.strip() for tag in self.tags):
            raise ValueError("tags must contain non-blank strings")
        normalized = tuple(tag.strip() for tag in self.tags)
        if len(set(normalized)) != len(normalized):
            raise ValueError("tags must not contain duplicates")
        object.__setattr__(self, "tags", normalized)


def _require_non_blank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")


def _validate_tags(tags: tuple[str, ...], field_name: str) -> None:
    if any(not isinstance(tag, str) or not tag.strip() for tag in tags):
        raise ValueError(f"{field_name} must contain non-blank strings")
    normalized = tuple(tag.strip() for tag in tags)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
