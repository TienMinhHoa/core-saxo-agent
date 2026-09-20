from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pytest

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.documents.ports import ArtifactRepository
from saxophone.extraction.models import PdfExtractionRequest, PdfExtractionResult
from saxophone.extraction.ports import PdfExtractor
from saxophone.workflows.process_document import ProcessAndPersistDocument, ProcessDocument


def _artifact(kind: ArtifactKind, name: str, payload: bytes) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=name,
        version="v1",
        kind=kind,
        media_type="application/octet-stream",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def _request() -> PdfExtractionRequest:
    source = b"pdf"
    return PdfExtractionRequest(
        document_ref="doc-1",
        source=_artifact(ArtifactKind.SOURCE_PDF, "source", source),
        source_version="source-v1",
        correlation_id="corr-1",
        model_profile="extract-v1",
    )


def _result() -> PdfExtractionResult:
    return PdfExtractionResult(
        document_ref="doc-1",
        source_version="source-v1",
        markdown=_artifact(ArtifactKind.MARKDOWN, "markdown", b"md"),
        layout=_artifact(ArtifactKind.LAYOUT, "layout", b"layout"),
        manifest=_artifact(ArtifactKind.EXTRACTION_MANIFEST, "manifest", b"manifest"),
        coordinates=(),
        model_profile="extract-v1",
    )


@dataclass
class FakeArtifacts(ArtifactRepository):
    stored: dict[str, bytes]

    async def put(self, artifact: ArtifactRef, payload: bytes) -> None:
        self.stored[artifact.artifact_id] = payload

    async def get(self, artifact: ArtifactRef) -> bytes:
        return self.stored[artifact.artifact_id]


@dataclass
class FakeExtractor(PdfExtractor):
    result: PdfExtractionResult

    async def extract(self, request: PdfExtractionRequest) -> PdfExtractionResult:
        return self.result


class FakePayloads:
    async def fetch(self, result: PdfExtractionResult) -> dict[str, bytes]:
        return {"markdown": b"md", "layout": b"layout", "manifest": b"manifest"}


@pytest.mark.anyio
async def test_process_and_persist_document_transfers_all_validated_outputs() -> None:
    result = _result()
    artifacts = FakeArtifacts({"source": b"pdf"})
    workflow = ProcessAndPersistDocument(
        ProcessDocument(artifacts, FakeExtractor(result)), FakePayloads(), artifacts
    )

    persisted = await workflow.execute(_request())

    assert persisted is result
    assert artifacts.stored == {
        "source": b"pdf",
        "markdown": b"md",
        "layout": b"layout",
        "manifest": b"manifest",
    }


@pytest.mark.anyio
async def test_process_and_persist_document_rejects_incomplete_transfer_before_writes() -> None:
    result = _result()
    artifacts = FakeArtifacts({"source": b"pdf"})

    class MissingPayloads:
        async def fetch(self, result: PdfExtractionResult) -> dict[str, bytes]:
            return {"markdown": b"md"}

    workflow = ProcessAndPersistDocument(
        ProcessDocument(artifacts, FakeExtractor(result)), MissingPayloads(), artifacts
    )

    with pytest.raises(ValueError, match="missing extraction payload"):
        await workflow.execute(_request())

    assert artifacts.stored == {"source": b"pdf"}
