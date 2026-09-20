"""Provider-independent extraction contracts."""

from .models import (
    CoordinateSpace,
    ExtractionCoordinate,
    PdfExtractionRequest,
    PdfExtractionResult,
)
from .ports import ExtractionArtifactPayloadProvider, PdfExtractor
from .remote import RemotePdfExtractor

__all__ = [
    "CoordinateSpace",
    "ExtractionCoordinate",
    "PdfExtractionRequest",
    "PdfExtractionResult",
    "PdfExtractor",
    "ExtractionArtifactPayloadProvider",
    "RemotePdfExtractor",
]
