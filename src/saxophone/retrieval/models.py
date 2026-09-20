"""Validated DTOs for retrieval and evidence selection."""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ChunkHit:
    """A ranked search result independent of Chroma or another index SDK."""

    source_ref: str
    chunk_ref: str
    rank: int
    retrieval_version: str
    metadata: Mapping[str, object]
    semantic_score: float | None = None
    keyword_score: float | None = None
    fused_score: float | None = None

    def __post_init__(self) -> None:
        for name in ("source_ref", "chunk_ref", "retrieval_version"):
            _require_non_blank(name, getattr(self, name))
            _require_canonical(name, getattr(self, name))
        if self.rank < 1:
            raise ValueError("rank must be at least 1")
        if not isinstance(self.metadata, Mapping):
            raise ValueError("metadata must be a mapping")
        for name in ("semantic_score", "keyword_score", "fused_score"):
            score = getattr(self, name)
            if score is not None and not math.isfinite(score):
                raise ValueError(f"{name} must be finite")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    """Validated evidence allowed to cross from retrieval into chat."""

    query: str
    retrieval_version: str
    hits: tuple[ChunkHit, ...]
    selected_refs: tuple[str, ...]
    source_texts: Mapping[str, str]
    image_refs: tuple[str, ...] = ()
    insufficiency_reason: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank("query", self.query)
        _require_non_blank("retrieval_version", self.retrieval_version)
        if not isinstance(self.source_texts, Mapping):
            raise ValueError("source_texts must be a mapping")
        for ref, text in self.source_texts.items():
            _require_non_blank("source_text ref", ref)
            if not isinstance(text, str) or not text.strip():
                raise ValueError("source_texts values must not be blank")
        for name, refs in (("selected_refs", self.selected_refs), ("image_refs", self.image_refs)):
            if not isinstance(refs, tuple):
                raise ValueError(f"{name} must be a tuple")
        for name, refs in (("selected_refs", self.selected_refs), ("image_refs", self.image_refs)):
            if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
                raise ValueError(f"{name} must contain non-blank refs")
            if any(ref != ref.strip() for ref in refs):
                raise ValueError(f"{name} must contain canonical refs")
            if any(unicodedata.normalize("NFC", ref) != ref for ref in refs):
                raise ValueError(f"{name} must contain canonical refs")
        hit_refs = tuple(hit.chunk_ref for hit in self.hits)
        if len(set(self.selected_refs)) != len(self.selected_refs):
            raise ValueError("selected_refs must be unique")
        if len(set(self.image_refs)) != len(self.image_refs):
            raise ValueError("image_refs must be unique")
        if any(ref not in hit_refs for ref in self.selected_refs):
            raise ValueError("selected_refs must refer to evidence hits")
        if set(self.source_texts) != set(self.selected_refs):
            raise ValueError("source_texts must match selected_refs")
        if any(ref not in self.source_texts for ref in self.selected_refs):
            raise ValueError("source_texts must contain every selected ref")
        if not self.hits and not self.insufficiency_reason:
            raise ValueError("insufficiency_reason is required when evidence is empty")
        if self.hits and self.insufficiency_reason is not None:
            raise ValueError("insufficiency_reason requires an empty evidence set")
        object.__setattr__(self, "source_texts", MappingProxyType(dict(self.source_texts)))


def _require_non_blank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")


def _require_canonical(name: str, value: str) -> None:
    if value != value.strip() or unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"{name} must contain a canonical value")
