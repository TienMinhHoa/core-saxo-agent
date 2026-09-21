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
from .layout import RAW_PDF_RASTER_SPACE, finite_number, normalize_blocks

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
]
