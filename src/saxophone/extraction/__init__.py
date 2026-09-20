"""Provider-independent extraction contracts."""

from .models import (
    CoordinateSpace,
    ExtractionCoordinate,
    PdfExtractionRequest,
    PdfExtractionResult,
)
from .ports import PdfExtractor
from .remote import RemotePdfExtractor

__all__ = [
    "CoordinateSpace",
    "ExtractionCoordinate",
    "PdfExtractionRequest",
    "PdfExtractionResult",
    "PdfExtractor",
    "RemotePdfExtractor",
]
