from __future__ import annotations

import pytest

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.extraction.models import (
    CoordinateSpace,
    ExtractionCoordinate,
    PdfExtractionRequest,
    PdfExtractionResult,
)


def artifact(kind: ArtifactKind) -> ArtifactRef:
    return ArtifactRef(
        artifact_id="document-123/output",
        version="extract-v1",
        kind=kind,
        media_type="application/octet-stream",
        sha256="a" * 64,
        size_bytes=0,
    )


def test_extraction_request_keeps_provider_independent_input_contract() -> None:
    request = PdfExtractionRequest(
        document_ref="document-123",
        source=artifact(ArtifactKind.SOURCE_PDF),
        source_version="source-v1",
        correlation_id="request-123",
        model_profile="pdf-layout-v1",
    )

    assert request.document_ref == "document-123"
    assert request.source.kind is ArtifactKind.SOURCE_PDF
    assert request.model_profile == "pdf-layout-v1"


def test_coordinate_preserves_explicit_page_and_markdown_spaces() -> None:
    coordinate = ExtractionCoordinate(
        coordinate_space=CoordinateSpace.RAW_RASTER,
        page_index=2,
        markdown_line_start=18,
        markdown_line_end=21,
        bbox=(10.0, 20.0, 100.0, 200.0),
    )

    assert coordinate.page_index == 2
    assert coordinate.coordinate_space is CoordinateSpace.RAW_RASTER
    assert coordinate.bbox == (10.0, 20.0, 100.0, 200.0)


def test_extraction_result_requires_expected_artifact_kinds() -> None:
    result = PdfExtractionResult(
        document_ref="document-123",
        source_version="source-v1",
        markdown=artifact(ArtifactKind.MARKDOWN),
        layout=artifact(ArtifactKind.LAYOUT),
        manifest=artifact(ArtifactKind.EXTRACTION_MANIFEST),
        coordinates=(),
        model_profile="pdf-layout-v1",
    )

    assert result.manifest.kind is ArtifactKind.EXTRACTION_MANIFEST
    assert result.coordinates == ()

    with pytest.raises(ValueError, match="markdown must have kind"):
        PdfExtractionResult(
            document_ref="document-123",
            source_version="source-v1",
            markdown=artifact(ArtifactKind.LAYOUT),
            layout=artifact(ArtifactKind.LAYOUT),
            manifest=artifact(ArtifactKind.EXTRACTION_MANIFEST),
            coordinates=(),
            model_profile="pdf-layout-v1",
        )


@pytest.mark.parametrize(
    "document_ref",
    ["../document-123", "document/123", "document-123\n", "document-cafe\u0301"],
)
def test_extraction_request_rejects_unsafe_document_reference(document_ref: str) -> None:
    with pytest.raises(ValueError, match="document_ref"):
        PdfExtractionRequest(
            document_ref=document_ref,
            source=artifact(ArtifactKind.SOURCE_PDF),
            source_version="source-v1",
            correlation_id="request-123",
            model_profile="pdf-layout-v1",
        )


@pytest.mark.parametrize(
    "document_ref",
    ["../document-123", "document/123", "document-123\t", "document-cafe\u0301"],
)
def test_extraction_result_rejects_unsafe_document_reference(document_ref: str) -> None:
    with pytest.raises(ValueError, match="document_ref"):
        PdfExtractionResult(
            document_ref=document_ref,
            source_version="source-v1",
            markdown=artifact(ArtifactKind.MARKDOWN),
            layout=artifact(ArtifactKind.LAYOUT),
            manifest=artifact(ArtifactKind.EXTRACTION_MANIFEST),
            coordinates=(),
            model_profile="pdf-layout-v1",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("page_index", -1), ("markdown_line_start", 0), ("markdown_line_end", 0)],
)
def test_coordinate_rejects_invalid_positions(field: str, value: int) -> None:
    fields = {
        "coordinate_space": CoordinateSpace.PDF_PAGE,
        "page_index": 0,
        "markdown_line_start": 1,
        "markdown_line_end": 1,
        "bbox": None,
    }
    fields[field] = value

    with pytest.raises(ValueError, match=field):
        ExtractionCoordinate(**fields)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("coordinate_space", "raw_raster"),
        ("page_index", True),
        ("markdown_line_start", 1.5),
        ("markdown_line_end", False),
    ],
)
def test_coordinate_rejects_wrong_scalar_types(field: str, value: object) -> None:
    fields: dict[str, object] = {
        "coordinate_space": CoordinateSpace.PDF_PAGE,
        "page_index": 0,
        "markdown_line_start": 1,
        "markdown_line_end": 1,
        "bbox": None,
    }
    fields[field] = value

    with pytest.raises(ValueError, match=field):
        ExtractionCoordinate(**fields)  # type: ignore[arg-type]


def test_coordinate_rejects_mutable_bbox_container() -> None:
    with pytest.raises(ValueError, match="bbox must be a tuple"):
        ExtractionCoordinate(
            coordinate_space=CoordinateSpace.PDF_PAGE,
            page_index=0,
            markdown_line_start=1,
            markdown_line_end=1,
            bbox=[10.0, 20.0, 100.0, 200.0],  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("bbox", [(float("nan"), 0.0, 1.0, 1.0), (0.0, float("inf"), 1.0, 1.0), (0.0, 1.0, float("-inf"), 1.0)])
def test_coordinate_rejects_non_finite_bbox_values(bbox: tuple[float, ...]) -> None:
    with pytest.raises(ValueError, match="bbox"):
        ExtractionCoordinate(
            coordinate_space=CoordinateSpace.PDF_PAGE,
            page_index=0,
            markdown_line_start=1,
            markdown_line_end=1,
            bbox=bbox,
        )


@pytest.mark.parametrize(
    "bbox",
    [(10.0, 20.0, 10.0, 40.0), (10.0, 20.0, 30.0, 20.0), (30.0, 20.0, 10.0, 40.0)],
)
def test_coordinate_rejects_degenerate_or_reversed_bbox(bbox: tuple[float, ...]) -> None:
    with pytest.raises(ValueError, match="bbox"):
        ExtractionCoordinate(
            coordinate_space=CoordinateSpace.PDF_PAGE,
            page_index=0,
            markdown_line_start=1,
            markdown_line_end=1,
            bbox=bbox,
        )
