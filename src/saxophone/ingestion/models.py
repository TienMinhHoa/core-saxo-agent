"""Provider-independent DTOs for the Phase 4 ingestion boundary."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IngestionCommand:
    """Inputs required to run ingestion without leaking adapter details."""

    document_ref: str
    source_version: str
    chunking_profile: str
    tagging_profile: str
    embedding_profile: str
    index_profile: str
    access_scope: str

    def __post_init__(self) -> None:
        for name in (
            "document_ref",
            "source_version",
            "chunking_profile",
            "tagging_profile",
            "embedding_profile",
            "index_profile",
            "access_scope",
        ):
            _require_non_blank(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class EmbeddingRecord:
    """A validated vector ready for a vector-index port."""

    chunk_id: str
    source_version: str
    model_profile: str
    vector: tuple[float, ...]

    def __post_init__(self) -> None:
        _require_non_blank("chunk_id", self.chunk_id)
        _require_non_blank("source_version", self.source_version)
        _require_non_blank("model_profile", self.model_profile)
        if not self.vector:
            raise ValueError("vector must not be empty")
        if any(not math.isfinite(value) for value in self.vector):
            raise ValueError("vector values must be finite")

    @property
    def dimension(self) -> int:
        return len(self.vector)


@dataclass(frozen=True, slots=True)
class IngestionReport:
    """Auditable counters describing one synchronous ingestion attempt."""

    document_ref: str
    source_version: str
    chunk_count: int
    paragraph_count: int
    tagged_paragraph_count: int
    failed_paragraph_count: int
    embedded_count: int
    reused_embedding_count: int
    skipped_count: int
    index_version: str
    indexed: bool
    warnings: tuple[str, ...]
    errors: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_blank("document_ref", self.document_ref)
        _require_non_blank("source_version", self.source_version)
        _require_non_blank("index_version", self.index_version)
        for name in (
            "chunk_count",
            "paragraph_count",
            "tagged_paragraph_count",
            "failed_paragraph_count",
            "embedded_count",
            "reused_embedding_count",
            "skipped_count",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")
        if self.tagged_paragraph_count > self.paragraph_count:
            raise ValueError("tagged_paragraph_count must not exceed paragraph_count")
        if self.failed_paragraph_count and self.indexed:
            raise ValueError("failed_count prevents indexed=True")
        if self.errors and self.indexed:
            raise ValueError("errors prevent indexed=True")


def _require_non_blank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")
