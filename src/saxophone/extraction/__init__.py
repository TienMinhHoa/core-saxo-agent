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
]
