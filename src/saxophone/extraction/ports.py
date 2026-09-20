"""Application ports for provider-independent PDF extraction."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from .models import PdfExtractionRequest, PdfExtractionResult


class PdfExtractor(Protocol):
    """Async boundary for an external PDF extraction service."""

    async def extract(self, request: PdfExtractionRequest) -> PdfExtractionResult:
        """Extract and validate a PDF without exposing provider details."""


class ExtractionArtifactPayloadProvider(Protocol):
    """Fetch output bytes through a controlled transfer boundary."""

    async def fetch(
        self, result: PdfExtractionResult
    ) -> Mapping[str, bytes]:
        """Return payloads for the output names declared by an extraction result."""
