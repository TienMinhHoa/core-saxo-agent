"""Stable facade for provider-independent extraction contracts and policies."""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "CoordinateSpace": (".models", "CoordinateSpace"),
    "ExtractionCoordinate": (".models", "ExtractionCoordinate"),
    "PdfExtractionRequest": (".models", "PdfExtractionRequest"),
    "PdfExtractionResult": (".models", "PdfExtractionResult"),
    "ExtractionArtifactPayloadProvider": (".ports", "ExtractionArtifactPayloadProvider"),
    "PdfExtractor": (".ports", "PdfExtractor"),
    "PersistExtractionArtifacts": (".persistence", "PersistExtractionArtifacts"),
    "RepositoryExtractionArtifactPayloadProvider": (
        ".persistence",
        "RepositoryExtractionArtifactPayloadProvider",
    ),
    "RemotePdfExtractor": (".remote", "RemotePdfExtractor"),
    "RAW_PDF_RASTER_SPACE": (".layout", "RAW_PDF_RASTER_SPACE"),
    "normalize_blocks": (".layout", "normalize_blocks"),
    "finite_number": (".layout", "finite_number"),
    "is_raw_pdf_raster_space": (".layout", "is_raw_pdf_raster_space"),
    "read_layout_pages": (".layout_view", "read_layout_pages"),
    "render_pdf_pages": (".pdf_pages", "render_pdf_pages"),
}

# Keep wildcard imports limited to provider-independent extraction contracts.
_ACTIVE_EXPORTS = (
    "CoordinateSpace",
    "ExtractionCoordinate",
    "PdfExtractionRequest",
    "PdfExtractionResult",
    "ExtractionArtifactPayloadProvider",
    "PdfExtractor",
)

__all__ = list(_ACTIVE_EXPORTS)


def __getattr__(name: str) -> Any:
    """Load extraction implementations only when a public symbol is used."""

    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value
