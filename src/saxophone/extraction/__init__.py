"""Provider-independent extraction contracts."""

from .models import (
    CoordinateSpace,
    ExtractionCoordinate,
    PdfExtractionRequest,
    PdfExtractionResult,
)
from .ports import ExtractionArtifactPayloadProvider, PdfExtractor
from .persistence import (
    PersistExtractionArtifacts,
    RepositoryExtractionArtifactPayloadProvider,
)
from .remote import RemotePdfExtractor
from .layout import (
    RAW_PDF_RASTER_SPACE,
    finite_number,
    is_raw_pdf_raster_space,
    normalize_blocks,
)
from .layout_view import read_layout_pages
from .pdf_pages import render_pdf_pages

__all__ = [
    "CoordinateSpace",
    "ExtractionCoordinate",
    "PdfExtractionRequest",
    "PdfExtractionResult",
    "PdfExtractor",
    "ExtractionArtifactPayloadProvider",
    "PersistExtractionArtifacts",
    "RemotePdfExtractor",
    "RepositoryExtractionArtifactPayloadProvider",
    "RAW_PDF_RASTER_SPACE",
    "normalize_blocks",
    "finite_number",
    "is_raw_pdf_raster_space",
    "read_layout_pages",
    "render_pdf_pages",
]
