from __future__ import annotations

import hashlib

import pytest

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.extraction.models import PdfExtractionResult
from saxophone.extraction.persistence import PersistExtractionArtifacts


def _artifact(kind: ArtifactKind, artifact_id: str, payload: bytes) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        version="v1",
        kind=kind,
        media_type="application/octet-stream",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def _result() -> tuple[PdfExtractionResult, dict[str, bytes]]:
    payloads = {
        "markdown": b"# extracted",
        "layout": b"layout-json",
        "manifest": b"manifest-json",
    }
    result = PdfExtractionResult(
        document_ref="doc-1",
        source_version="source-v1",
        markdown=_artifact(ArtifactKind.MARKDOWN, "doc-1/markdown", payloads["markdown"]),
        layout=_artifact(ArtifactKind.LAYOUT, "doc-1/layout", payloads["layout"]),
        manifest=_artifact(
            ArtifactKind.EXTRACTION_MANIFEST,
            "doc-1/manifest",
            payloads["manifest"],
        ),
        coordinates=(),
        model_profile="extractor-v1",
    )
    return result, payloads


class FakeArtifacts:
    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}

    async def put(self, artifact: ArtifactRef, payload: bytes) -> None:
        if len(payload) != artifact.size_bytes:
            raise ValueError("payload size mismatch")
        if hashlib.sha256(payload).hexdigest() != artifact.sha256:
            raise ValueError("payload checksum mismatch")
        self.saved[artifact.artifact_id] = payload


@pytest.mark.anyio
async def test_persist_extraction_artifacts_writes_all_typed_outputs() -> None:
    result, payloads = _result()
    repository = FakeArtifacts()

    persisted = await PersistExtractionArtifacts(repository).execute(result, payloads)

    assert persisted is result
    assert repository.saved == {
        "doc-1/markdown": payloads["markdown"],
        "doc-1/layout": payloads["layout"],
        "doc-1/manifest": payloads["manifest"],
    }


@pytest.mark.anyio
async def test_persist_extraction_artifacts_rejects_missing_named_output() -> None:
    result, payloads = _result()
    repository = FakeArtifacts()
    del payloads["manifest"]

    with pytest.raises(ValueError, match="manifest"):
        await PersistExtractionArtifacts(repository).execute(result, payloads)

    assert repository.saved == {}


@pytest.mark.anyio
async def test_persist_extraction_artifacts_prevalidates_payloads_before_writing() -> None:
    result, payloads = _result()
    repository = FakeArtifacts()
    payloads["layout"] = b"tampered"

    with pytest.raises(ValueError, match="size|checksum"):
        await PersistExtractionArtifacts(repository).execute(result, payloads)

    assert repository.saved == {}
