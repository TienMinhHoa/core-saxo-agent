"""Document processing orchestration at the application boundary."""

from __future__ import annotations

import hashlib

from saxophone.documents.ports import ArtifactRepository
from saxophone.extraction.models import PdfExtractionRequest, PdfExtractionResult
from saxophone.extraction.ports import PdfExtractor


class ProcessDocument:
    """Verify an owned source artifact before invoking remote extraction."""

    def __init__(self, artifacts: ArtifactRepository, extractor: PdfExtractor) -> None:
        self._artifacts = artifacts
        self._extractor = extractor

    async def execute(self, request: PdfExtractionRequest) -> PdfExtractionResult:
        payload = await self._artifacts.get(request.source)
        if len(payload) != request.source.size_bytes:
            raise ValueError("source artifact payload size does not match metadata")
        if hashlib.sha256(payload).hexdigest() != request.source.sha256:
            raise ValueError("source artifact payload checksum does not match metadata")
        return await self._extractor.extract(request)
