from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace

import pytest

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.extraction.models import PdfExtractionRequest
from saxophone.extraction.remote import RemotePdfExtractor, _required_artifact
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


def test_remote_pdf_extractor_maps_json_artifact_envelopes() -> None:
    class FakeClient:
        async def invoke(self, request: ModelRequest) -> ModelResponse:
            return ModelResponse(
                task=ModelTask.PDF_EXTRACT,
                model="extractor-v1",
                response_schema="pdf-extraction-v1",
                output={
                    name: {
                        "artifact_id": name,
                        "version": "v1",
                        "kind": kind.value,
                        "media_type": media_type,
                        "sha256": hashlib.sha256(name.encode()).hexdigest(),
                        "size_bytes": len(name),
                    }
                    for name, kind, media_type in (
                        ("markdown", ArtifactKind.MARKDOWN, "text/markdown"),
                        ("layout", ArtifactKind.LAYOUT, "application/json"),
                        ("manifest", ArtifactKind.EXTRACTION_MANIFEST, "application/json"),
                    )
                },
                source_version="source-v1",
            )

    result = asyncio.run(
        RemotePdfExtractor(FakeClient(), model="extractor-v1").extract(_request())
    )

    assert result.markdown.artifact_id == "markdown"
    assert result.markdown.kind is ArtifactKind.MARKDOWN
    assert result.markdown.media_type == "text/markdown"
    assert result.layout.media_type == "application/json"


@pytest.mark.parametrize("field", ["kind", "sha256", "size_bytes"])
def test_remote_pdf_extractor_rejects_invalid_json_artifact_metadata(field: str) -> None:
    class FakeClient:
        async def invoke(self, request: ModelRequest) -> ModelResponse:
            artifact = {
                "artifact_id": "markdown",
                "version": "v1",
                "kind": ArtifactKind.MARKDOWN.value,
                "media_type": "text/markdown",
                "sha256": hashlib.sha256(b"markdown").hexdigest(),
                "size_bytes": len("markdown"),
            }
            artifact[field] = {
                "kind": "not-an-artifact"
            } if field == "kind" else ("not-a-digest" if field == "sha256" else -1)
            return ModelResponse(
                task=ModelTask.PDF_EXTRACT,
                model="extractor-v1",
                response_schema="pdf-extraction-v1",
                output={"markdown": artifact},
                source_version="source-v1",
            )

    with pytest.raises(ValueError, match=field):
        asyncio.run(RemotePdfExtractor(FakeClient(), model="extractor-v1").extract(_request()))


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


def test_remote_pdf_extractor_rejects_source_version_drift() -> None:
    class FakeClient:
        async def invoke(self, request: ModelRequest) -> ModelResponse:
            return ModelResponse(
                task=ModelTask.PDF_EXTRACT,
                model="extractor-v1",
                response_schema="pdf-extraction-v1",
                output={
                    "markdown": _artifact("markdown", ArtifactKind.MARKDOWN),
                    "layout": _artifact("layout", ArtifactKind.LAYOUT),
                    "manifest": _artifact("manifest", ArtifactKind.EXTRACTION_MANIFEST),
                },
                source_version="different-source-v1",
            )

    with pytest.raises(ValueError, match="source_version"):
        asyncio.run(RemotePdfExtractor(FakeClient(), model="extractor-v1").extract(_request()))


def test_remote_pdf_extractor_rejects_wrong_request_runtime_type() -> None:
    class FakeClient:
        async def invoke(self, request: ModelRequest) -> ModelResponse:
            raise AssertionError("provider must not be called for an invalid request")

    with pytest.raises(ValueError, match="request must be a PdfExtractionRequest"):
        asyncio.run(
            RemotePdfExtractor(FakeClient(), model="extractor-v1").extract(
                object()  # type: ignore[arg-type]
            )
        )


def test_remote_pdf_extractor_rejects_wrong_response_runtime_type() -> None:
    class FakeClient:
        async def invoke(self, request: ModelRequest) -> ModelResponse:
            return SimpleNamespace(
                task=ModelTask.PDF_EXTRACT,
                response_schema="pdf-extraction-v1",
                output={},
                source_version="source-v1",
            )  # type: ignore[return-value]

    with pytest.raises(ValueError, match="response must be a ModelResponse"):
        asyncio.run(RemotePdfExtractor(FakeClient(), model="extractor-v1").extract(_request()))


def test_remote_pdf_extractor_rejects_non_mapping_output_before_artifact_lookup() -> None:
    with pytest.raises(ValueError, match="model output must be a mapping"):
        _required_artifact([("markdown", object())], "markdown")  # type: ignore[arg-type]
