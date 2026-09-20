"""Typed DTOs for the Phase 3 PDF extraction boundary."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.documents.policies import is_safe_document_reference


class CoordinateSpace(StrEnum):
    """Coordinate spaces that must not be silently converted into each other."""

    PDF_PAGE = "pdf_page"
    RAW_RASTER = "raw_raster"
    OCR_RASTER = "ocr_raster"


@dataclass(frozen=True, slots=True)
class ExtractionCoordinate:
    """A source locator retaining page, markdown, and optional raster evidence."""

    coordinate_space: CoordinateSpace
    page_index: int
    markdown_line_start: int
    markdown_line_end: int
    bbox: tuple[float, float, float, float] | None

    def __post_init__(self) -> None:
        if self.page_index < 0:
            raise ValueError("page_index must not be negative")
        if self.markdown_line_start <= 0:
            raise ValueError("markdown_line_start must be positive")
        if self.markdown_line_end < self.markdown_line_start:
            raise ValueError("markdown_line_end must not precede markdown_line_start")
        if self.bbox is not None:
            if (
                len(self.bbox) != 4
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value < 0
                    for value in self.bbox
                )
            ):
                raise ValueError("bbox must contain four non-negative coordinates")
            left, top, right, bottom = self.bbox
            if right <= left or bottom <= top:
                raise ValueError("bbox must have positive width and height")


@dataclass(frozen=True, slots=True)
class PdfExtractionRequest:
    """Input passed to an extractor without CLI, environment, or provider details."""

    document_ref: str
    source: ArtifactRef
    source_version: str
    correlation_id: str
    model_profile: str

    def __post_init__(self) -> None:
        _require_safe_document_reference(self.document_ref)
        _require_non_blank("source_version", self.source_version)
        _require_non_blank("correlation_id", self.correlation_id)
        _require_non_blank("model_profile", self.model_profile)
        if self.source.kind is not ArtifactKind.SOURCE_PDF:
            raise ValueError("source must have kind source_pdf")


@dataclass(frozen=True, slots=True)
class PdfExtractionResult:
    """Validated extraction output that can be persisted by an application use case."""

    document_ref: str
    source_version: str
    markdown: ArtifactRef
    layout: ArtifactRef
    manifest: ArtifactRef
    coordinates: tuple[ExtractionCoordinate, ...]
    model_profile: str

    def __post_init__(self) -> None:
        _require_safe_document_reference(self.document_ref)
        _require_non_blank("source_version", self.source_version)
        _require_non_blank("model_profile", self.model_profile)
        _require_kind("markdown", self.markdown, ArtifactKind.MARKDOWN)
        _require_kind("layout", self.layout, ArtifactKind.LAYOUT)
        _require_kind("manifest", self.manifest, ArtifactKind.EXTRACTION_MANIFEST)


def _require_kind(name: str, artifact: ArtifactRef, expected: ArtifactKind) -> None:
    if artifact.kind is not expected:
        raise ValueError(f"{name} must have kind {expected.value}")


def _require_non_blank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")


def _require_safe_document_reference(value: str) -> None:
    if not is_safe_document_reference(value):
        raise ValueError("document_ref must be a safe document reference")
