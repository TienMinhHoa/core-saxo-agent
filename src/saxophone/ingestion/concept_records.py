"""Validated vector-index projections for canonical concepts."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from saxophone.tagging.concepts import ConceptCandidate


@dataclass(frozen=True, slots=True)
class ConceptVectorRecord:
    """One canonical concept projection for the ``concept_catalog`` index."""

    record_id: str
    canonical_label: str
    normalized_label: str
    search_text: str
    embedding: tuple[float, ...]
    usage_count: int
    embedding_input_hash: str
    embedding_model: str
    embedding_dimensions: int
    index_version: str
    metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        for name in (
            "record_id",
            "canonical_label",
            "normalized_label",
            "search_text",
            "embedding_input_hash",
            "embedding_model",
            "index_version",
        ):
            _require_non_blank(name, getattr(self, name))
        expected_id = _record_id(self.normalized_label)
        if self.record_id != expected_id:
            raise ValueError("record_id must be derived from normalized_label")
        if not self.embedding:
            raise ValueError("embedding must not be empty")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in self.embedding
        ):
            raise ValueError("embedding values must be finite numbers")
        if self.embedding_dimensions != len(self.embedding):
            raise ValueError("embedding_dimensions must match embedding length")
        if isinstance(self.usage_count, bool) or not isinstance(self.usage_count, int):
            raise ValueError("usage_count must be a non-negative integer")
        if self.usage_count < 0:
            raise ValueError("usage_count must be a non-negative integer")
        if not _is_sha256(self.embedding_input_hash):
            raise ValueError("embedding_input_hash must be a SHA-256 hex digest")
        if not isinstance(self.metadata, Mapping):
            raise ValueError("metadata must be a mapping")
        object.__setattr__(self, "embedding", tuple(float(value) for value in self.embedding))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


def build_concept_vector_record(
    candidate: ConceptCandidate,
    *,
    embedding: Sequence[float],
    embedding_model: str,
    index_version: str,
    max_examples: int = 3,
) -> ConceptVectorRecord:
    """Build a deterministic catalog record from a validated concept candidate."""

    if not isinstance(candidate, ConceptCandidate):
        raise ValueError("candidate must be a ConceptCandidate")
    if isinstance(embedding, (str, bytes)) or not isinstance(embedding, Sequence):
        raise ValueError("embedding must be a sequence of finite numbers")
    if not embedding:
        raise ValueError("embedding must not be empty")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in embedding
    ):
        raise ValueError("embedding values must be finite numbers")
    _require_non_blank("embedding_model", embedding_model)
    _require_non_blank("index_version", index_version)
    if isinstance(max_examples, bool) or not isinstance(max_examples, int) or max_examples < 1:
        raise ValueError("max_examples must be a positive integer")

    examples = candidate.examples[:max_examples]
    search_lines = [candidate.canonical_label]
    search_lines.extend(f"{example.header}: {example.excerpt}" for example in examples)
    search_text = "\n".join(search_lines)
    normalized_label = candidate.normalized_label
    return ConceptVectorRecord(
        record_id=_record_id(normalized_label),
        canonical_label=candidate.canonical_label,
        normalized_label=normalized_label,
        search_text=search_text,
        embedding=tuple(embedding),
        usage_count=candidate.usage_count,
        embedding_input_hash=_sha256(search_text),
        embedding_model=embedding_model.strip(),
        embedding_dimensions=len(embedding),
        index_version=index_version.strip(),
        metadata={
            "canonical_label": candidate.canonical_label,
            "normalized_label": normalized_label,
            "usage_count": candidate.usage_count,
            "embedding_input_hash": _sha256(search_text),
            "embedding_model": embedding_model.strip(),
            "embedding_dimensions": len(embedding),
            "index_version": index_version.strip(),
        },
    )


def _record_id(normalized_label: str) -> str:
    return f"concept::{_sha256(normalized_label)}"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _require_non_blank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")
