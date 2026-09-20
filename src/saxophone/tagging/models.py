"""Immutable DTOs for paragraph-level topic tag generation."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


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
