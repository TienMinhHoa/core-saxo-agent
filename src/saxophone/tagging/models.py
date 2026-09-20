"""Immutable DTOs for paragraph-level topic tag generation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParagraphBlock:
    """A source paragraph identified without changing its source text."""

    paragraph_id: str
    chunk_id: str
    ordinal: int
    text: str

    def __post_init__(self) -> None:
        for name in ("paragraph_id", "chunk_id", "text"):
            _require_non_blank(name, getattr(self, name))
        if self.ordinal < 0:
            raise ValueError("ordinal must not be negative")


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
