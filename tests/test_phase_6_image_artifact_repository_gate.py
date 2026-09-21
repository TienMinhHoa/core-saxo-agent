from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import pytest

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.platform.artifacts import (
    LocalArtifactRepository,
    RepositoryBackedImageArtifactGate,
)


class _Resolver:
    def __init__(self, artifact: ArtifactRef) -> None:
        self.artifact = artifact

    async def resolve(self, image_ref: str) -> ArtifactRef:
        assert image_ref == "images/page-1.png"
        return self.artifact


class _Repository:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    async def get(self, artifact: ArtifactRef) -> bytes:
        return self.payload


def _artifact(payload: bytes = b"image-bytes") -> ArtifactRef:
    return ArtifactRef(
        artifact_id="document-1/images/page-1.png",
        version="image-v1",
        kind=ArtifactKind.IMAGE,
        media_type="image/png",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


@pytest.mark.anyio
async def test_repository_backed_gate_resolves_and_verifies_image_bytes(
    tmp_path: Path,
) -> None:
    payload = b"image-bytes"
    artifact = _artifact(payload)
    repository = LocalArtifactRepository(tmp_path)
    await repository.put(artifact, payload)

    gate = RepositoryBackedImageArtifactGate(repository, _Resolver(artifact))

    assert await gate.validate(("images/page-1.png",)) == ("images/page-1.png",)


@pytest.mark.anyio
async def test_repository_backed_gate_rejects_non_image_artifact(tmp_path: Path) -> None:
    artifact = ArtifactRef(
        artifact_id="document-1/manifest.json",
        version="manifest-v1",
        kind=ArtifactKind.EXTRACTION_MANIFEST,
        media_type="application/json",
        sha256=hashlib.sha256(b"{}").hexdigest(),
        size_bytes=2,
    )
    repository = LocalArtifactRepository(tmp_path)
    await repository.put(artifact, b"{}")

    gate = RepositoryBackedImageArtifactGate(repository, _Resolver(artifact))

    with pytest.raises(ValueError, match="IMAGE"):
        await gate.validate(("images/page-1.png",))


@pytest.mark.anyio
async def test_repository_backed_gate_rejects_tampered_payload(tmp_path: Path) -> None:
    payload = b"image-bytes"
    artifact = _artifact(payload)
    repository = LocalArtifactRepository(tmp_path)
    await repository.put(artifact, payload)
    path = tmp_path / artifact.artifact_id / artifact.version
    path.write_bytes(b"tampered!!!")

    gate = RepositoryBackedImageArtifactGate(repository, _Resolver(artifact))

    with pytest.raises(ValueError, match="sha256"):
        await gate.validate(("images/page-1.png",))


@pytest.mark.anyio
async def test_repository_backed_gate_hashes_payload_in_bounded_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"image-bytes"
    artifact = _artifact(payload)
    caller_thread = threading.get_ident()
    observed_threads: list[int] = []
    from saxophone.platform import artifacts as artifacts_module

    real_validate_payload = artifacts_module._validate_payload

    def observe_validate_payload(
        artifact_ref: ArtifactRef, payload_bytes: bytes
    ) -> None:
        observed_threads.append(threading.get_ident())
        real_validate_payload(artifact_ref, payload_bytes)

    monkeypatch.setattr(
        artifacts_module, "_validate_payload", observe_validate_payload
    )
    gate = RepositoryBackedImageArtifactGate(
        _Repository(payload), _Resolver(artifact)
    )

    assert await gate.validate(("images/page-1.png",)) == ("images/page-1.png",)
    assert observed_threads
    assert all(thread_id != caller_thread for thread_id in observed_threads)
