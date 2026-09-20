from __future__ import annotations

import hashlib
from dataclasses import dataclass
from dataclasses import replace

import pytest

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.documents.ports import ArtifactRepository
from saxophone.extraction.models import PdfExtractionRequest, PdfExtractionResult
from saxophone.extraction.ports import PdfExtractor
from saxophone.workflows.process_document import ProcessDocument


def _source(payload: bytes = b"pdf") -> ArtifactRef:
    return ArtifactRef(
        artifact_id="doc-1/source",
        version="v1",
        kind=ArtifactKind.SOURCE_PDF,
        media_type="application/pdf",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def _result() -> PdfExtractionResult:
    payload = b"artifact"

    def artifact(kind: ArtifactKind, artifact_id: str) -> ArtifactRef:
        return ArtifactRef(
            artifact_id=artifact_id,
            version="v1",
            kind=kind,
            media_type="application/octet-stream",
            sha256=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
        )

    return PdfExtractionResult(
        document_ref="doc-1",
        source_version="source-v1",
        markdown=artifact(ArtifactKind.MARKDOWN, "markdown"),
        layout=artifact(ArtifactKind.LAYOUT, "layout"),
        manifest=artifact(ArtifactKind.EXTRACTION_MANIFEST, "manifest"),
        coordinates=(),
        model_profile="extractor-v1",
    )


@dataclass
class FakeArtifacts(ArtifactRepository):
    payload: bytes | None

    async def put(self, artifact: ArtifactRef, payload: bytes) -> None:
        self.payload = payload

    async def get(self, artifact: ArtifactRef) -> bytes:
        if self.payload is None:
            raise FileNotFoundError(artifact.artifact_id)
        return self.payload


@dataclass
class FakeExtractor(PdfExtractor):
    calls: list[PdfExtractionRequest]
    result: PdfExtractionResult

    async def extract(self, request: PdfExtractionRequest) -> PdfExtractionResult:
        self.calls.append(request)
        return self.result


@pytest.mark.anyio
async def test_process_document_verifies_source_before_extraction() -> None:
    artifacts = FakeArtifacts(b"pdf")
    extractor = FakeExtractor([], _result())
    use_case = ProcessDocument(artifacts, extractor)
    request = PdfExtractionRequest(
        document_ref="doc-1",
        source=_source(),
        source_version="source-v1",
        correlation_id="corr-1",
        model_profile="extractor-v1",
    )

    result = await use_case.execute(request)

    assert extractor.calls == [request]
    assert result is extractor.result


@pytest.mark.anyio
async def test_process_document_rejects_missing_source_without_calling_extractor() -> None:
    artifacts = FakeArtifacts(None)
    extractor = FakeExtractor([], _result())
    use_case = ProcessDocument(artifacts, extractor)
    request = PdfExtractionRequest(
        document_ref="doc-1",
        source=_source(),
        source_version="source-v1",
        correlation_id="corr-1",
        model_profile="extractor-v1",
    )

    with pytest.raises(FileNotFoundError):
        await use_case.execute(request)

    assert extractor.calls == []


@pytest.mark.anyio
async def test_process_document_rejects_source_size_mismatch_without_calling_extractor() -> None:
    artifacts = FakeArtifacts(b"pdf")
    extractor = FakeExtractor([], _result())
    use_case = ProcessDocument(artifacts, extractor)
    request = PdfExtractionRequest(
        document_ref="doc-1",
        source=replace(_source(), size_bytes=99),
        source_version="source-v1",
        correlation_id="corr-1",
        model_profile="extractor-v1",
    )

    with pytest.raises(ValueError, match="size"):
        await use_case.execute(request)

    assert extractor.calls == []


@pytest.mark.anyio
async def test_process_document_rejects_source_checksum_mismatch_without_calling_extractor() -> None:
    artifacts = FakeArtifacts(b"bad")
    extractor = FakeExtractor([], _result())
    use_case = ProcessDocument(artifacts, extractor)
    request = PdfExtractionRequest(
        document_ref="doc-1",
        source=_source(b"pdf"),
        source_version="source-v1",
        correlation_id="corr-1",
        model_profile="extractor-v1",
    )

    with pytest.raises(ValueError, match="checksum"):
        await use_case.execute(request)

    assert extractor.calls == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("document_ref", "doc-other"),
        ("source_version", "source-other"),
        ("model_profile", "extractor-other"),
    ],
)
async def test_process_document_rejects_result_that_does_not_match_request(
    field: str, expected: str
) -> None:
    artifacts = FakeArtifacts(b"pdf")
    extractor_result = _result()
    extractor_result = replace(extractor_result, **{field: expected})
    extractor = FakeExtractor([], extractor_result)
    use_case = ProcessDocument(artifacts, extractor)
    request = PdfExtractionRequest(
        document_ref="doc-1",
        source=_source(),
        source_version="source-v1",
        correlation_id="corr-1",
        model_profile="extractor-v1",
    )

    with pytest.raises(ValueError, match=field):
        await use_case.execute(request)
