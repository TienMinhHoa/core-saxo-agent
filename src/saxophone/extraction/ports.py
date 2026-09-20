"""Application ports for provider-independent PDF extraction."""

from __future__ import annotations

from typing import Protocol

from .models import PdfExtractionRequest, PdfExtractionResult


class PdfExtractor(Protocol):
    """Async boundary for an external PDF extraction service."""

    async def extract(self, request: PdfExtractionRequest) -> PdfExtractionResult:
        """Extract and validate a PDF without exposing provider details."""
