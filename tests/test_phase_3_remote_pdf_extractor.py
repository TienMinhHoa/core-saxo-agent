from __future__ import annotations

import asyncio
import hashlib

import pytest

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.extraction.models import PdfExtractionRequest
from saxophone.extraction.remote import RemotePdfExtractor
from saxophone.platform.model_client import ModelRequest, ModelResponse, ModelTask


def _artifact(name: str, kind: ArtifactKind) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=name,
        version="v1",
        kind=kind,
        media_type="application/octet-stream",
        sha256=hashlib.sha256(name.encode()).hexdigest(),
        size_bytes=len(name),
    )


def _request() -> PdfExtractionRequest:
    return PdfExtractionRequest(
        document_ref="doc-1",
        source=_artifact("source", ArtifactKind.SOURCE_PDF),
        source_version="source-v1",
        correlation_id="corr-1",
        model_profile="extractor-v1",
    )


def test_remote_pdf_extractor_maps_typed_model_result() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.request: ModelRequest | None = None

        async def invoke(self, request: ModelRequest) -> ModelResponse:
            self.request = request
            return ModelResponse(
                task=ModelTask.PDF_EXTRACT,
                model="extractor-v1",
                response_schema="pdf-extraction-v1",
                output={
                    "markdown": _artifact("markdown", ArtifactKind.MARKDOWN),
                    "layout": _artifact("layout", ArtifactKind.LAYOUT),
                    "manifest": _artifact("manifest", ArtifactKind.EXTRACTION_MANIFEST),
                },
                source_version="source-v1",
            )

    client = FakeClient()
    result = asyncio.run(
        RemotePdfExtractor(client, model="extractor-v1").extract(_request())
    )

    assert result.document_ref == "doc-1"
    assert result.markdown.kind is ArtifactKind.MARKDOWN
    assert client.request is not None
    assert client.request.task is ModelTask.PDF_EXTRACT
    assert client.request.input["source_artifact_id"] == "source"
    assert client.request.metadata["correlation_id"] == "corr-1"


@pytest.mark.parametrize("field", ["markdown", "layout", "manifest"])
def test_remote_pdf_extractor_rejects_missing_artifact(field: str) -> None:
    class FakeClient:
        async def invoke(self, request: ModelRequest) -> ModelResponse:
            output = {
                "markdown": _artifact("markdown", ArtifactKind.MARKDOWN),
                "layout": _artifact("layout", ArtifactKind.LAYOUT),
                "manifest": _artifact("manifest", ArtifactKind.EXTRACTION_MANIFEST),
            }
            del output[field]
            return ModelResponse(
                task=ModelTask.PDF_EXTRACT,
                model="extractor-v1",
                response_schema="pdf-extraction-v1",
                output=output,
                source_version="source-v1",
            )

    with pytest.raises(ValueError, match=field):
        asyncio.run(RemotePdfExtractor(FakeClient(), model="extractor-v1").extract(_request()))


def test_remote_pdf_extractor_rejects_wrong_task_or_schema() -> None:
    class FakeClient:
        async def invoke(self, request: ModelRequest) -> ModelResponse:
            return ModelResponse(
                task=ModelTask.EMBED,
                model="extractor-v1",
                response_schema="other-v1",
                output={},
                source_version="source-v1",
            )

    with pytest.raises(ValueError, match="task"):
        asyncio.run(RemotePdfExtractor(FakeClient(), model="extractor-v1").extract(_request()))
