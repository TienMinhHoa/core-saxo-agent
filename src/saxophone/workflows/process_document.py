"""Document processing orchestration at the application boundary."""

from __future__ import annotations

import hashlib

from saxophone.documents.models import ArtifactKind
from saxophone.documents.ports import ArtifactRepository
from saxophone.extraction.models import PdfExtractionRequest, PdfExtractionResult
from saxophone.extraction.persistence import PersistExtractionArtifacts
from saxophone.extraction.ports import ExtractionArtifactPayloadProvider, PdfExtractor


class ProcessDocument:
    """Verify an owned source artifact before invoking remote extraction."""

    def __init__(self, artifacts: ArtifactRepository, extractor: PdfExtractor) -> None:
        self._artifacts = artifacts
        self._extractor = extractor

    async def execute(self, request: PdfExtractionRequest) -> PdfExtractionResult:
        if request.source.kind is not ArtifactKind.SOURCE_PDF:
            raise ValueError("source artifact must have kind source_pdf")
        if request.source.media_type != "application/pdf":
            raise ValueError("source artifact must have media type application/pdf")
        payload = await self._artifacts.get(request.source)
        if len(payload) != request.source.size_bytes:
            raise ValueError("source artifact payload size does not match metadata")
        if hashlib.sha256(payload).hexdigest() != request.source.sha256:
            raise ValueError("source artifact payload checksum does not match metadata")
        result = await self._extractor.extract(request)
        self._validate_result_scope(request, result)
        return result

    @staticmethod
    def _validate_result_scope(
        request: PdfExtractionRequest, result: PdfExtractionResult
    ) -> None:
        if result.document_ref != request.document_ref:
            raise ValueError("extraction result document_ref does not match request")
        if result.source_version != request.source_version:
            raise ValueError("extraction result source_version does not match request")
        if result.model_profile != request.model_profile:
            raise ValueError("extraction result model_profile does not match request")


class ProcessAndPersistDocument:
    """Run extraction and persist its verified outputs in one request boundary."""

    def __init__(
        self,
        process: ProcessDocument,
        payloads: ExtractionArtifactPayloadProvider,
        artifacts: ArtifactRepository,
    ) -> None:
        self._process = process
        self._payloads = payloads
        self._persist = PersistExtractionArtifacts(artifacts)

    async def execute(self, request: PdfExtractionRequest) -> PdfExtractionResult:
        result = await self._process.execute(request)
        payloads = await self._payloads.fetch(result)
        return await self._persist.execute(result, payloads)
