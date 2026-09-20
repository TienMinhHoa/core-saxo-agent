"""Typed knowledge records kept independently from artifacts and vector indexes."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """Full-fidelity metadata for one searchable document chunk.

    The record contains references to source artifacts, never their binary
    contents.  Vector-index adapters may project this record into scalar
    metadata, while the knowledge repository remains the source of truth.
    """

    chunk_id: str
    document_id: str
    source_version: str
    source_ref: str
    search_text: str
    content_hash: str
    page_start: int = -1
    page_end: int = -1
    heading_path: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    image_refs: tuple[str, ...] = ()
    paragraph_count: int = 0
    image_count: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "chunk_id",
            "document_id",
            "source_version",
            "source_ref",
            "search_text",
        ):
            _require_non_blank(field_name, getattr(self, field_name))
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_hash):
            raise ValueError("content_hash must be a lowercase 64-character hexadecimal digest")
        if self.page_start < -1 or self.page_end < -1:
            raise ValueError("page numbers must be -1 or positive")
        if self.page_start != -1 and self.page_end != -1 and self.page_end < self.page_start:
            raise ValueError("page_end must not be before page_start")
        if self.paragraph_count < 0 or self.image_count < 0:
            raise ValueError("content counts must not be negative")
        for field_name in ("heading_path", "tags", "image_refs"):
            values = getattr(self, field_name)
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{field_name} must contain non-blank strings")


def _require_non_blank(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
