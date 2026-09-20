from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pytest

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.documents.ports import ArtifactRepository
from saxophone.extraction.models import PdfExtractionResult
from saxophone.extraction.persistence import RepositoryExtractionArtifactPayloadProvider


def _artifact(kind: ArtifactKind, name: str, payload: bytes) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=name,
        version="v1",
        kind=kind,
        media_type="application/octet-stream",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def _result() -> PdfExtractionResult:
    return PdfExtractionResult(
        document_ref="doc-1",
        source_version="source-v1",
        markdown=_artifact(ArtifactKind.MARKDOWN, "markdown", b"md"),
        layout=_artifact(ArtifactKind.LAYOUT, "layout", b"layout"),
        manifest=_artifact(
            ArtifactKind.EXTRACTION_MANIFEST, "manifest", b"manifest"
        ),
        coordinates=(),
        model_profile="extract-v1",
    )


@dataclass
class FakeArtifacts(ArtifactRepository):
    payloads: dict[str, bytes]
    requested: list[str]

    async def put(self, artifact: ArtifactRef, payload: bytes) -> None:
        self.payloads[artifact.artifact_id] = payload

    async def get(self, artifact: ArtifactRef) -> bytes:
        self.requested.append(artifact.artifact_id)
        return self.payloads[artifact.artifact_id]


@pytest.mark.anyio
async def test_repository_payload_provider_fetches_all_declared_outputs() -> None:
    artifacts = FakeArtifacts(
        {"markdown": b"md", "layout": b"layout", "manifest": b"manifest"}, []
    )

    payloads = await RepositoryExtractionArtifactPayloadProvider(artifacts).fetch(
        _result()
    )

    assert payloads == {
        "markdown": b"md",
        "layout": b"layout",
        "manifest": b"manifest",
    }
    assert artifacts.requested == ["markdown", "layout", "manifest"]


@pytest.mark.anyio
async def test_repository_payload_provider_propagates_missing_artifact() -> None:
    artifacts = FakeArtifacts({"markdown": b"md"}, [])

    with pytest.raises(KeyError):
        await RepositoryExtractionArtifactPayloadProvider(artifacts).fetch(_result())
