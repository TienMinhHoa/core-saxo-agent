from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.documents.ports import ArtifactRepository
from saxophone.platform.artifacts import LocalArtifactRepository


def _artifact(*, artifact_id: str = "document-123/manifest") -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        version="extract-v1",
        kind=ArtifactKind.EXTRACTION_MANIFEST,
        media_type="application/json",
        sha256=hashlib.sha256(b"1234567").hexdigest(),
        size_bytes=7,
    )


def test_local_repository_implements_artifact_port_and_round_trips_bytes(
    tmp_path: Path,
) -> None:
    repository: ArtifactRepository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()

    asyncio.run(repository.put(artifact, b"1234567"))

    assert asyncio.run(repository.get(artifact)) == b"1234567"


def test_put_rejects_payload_that_does_not_match_declared_size_or_digest(
    tmp_path: Path,
) -> None:
    repository = LocalArtifactRepository(tmp_path)

    with pytest.raises(ValueError, match="size_bytes"):
        asyncio.run(repository.put(_artifact(), b"wrong"))

    with pytest.raises(ValueError, match="sha256"):
        asyncio.run(repository.put(_artifact(), b"7654321"))


def test_repository_does_not_allow_artifact_id_path_traversal(tmp_path: Path) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact(artifact_id="../outside")

    with pytest.raises(ValueError, match="artifact_id"):
        asyncio.run(repository.put(artifact, b"1234567"))


def test_put_is_atomic_and_does_not_leave_temporary_files(tmp_path: Path) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()

    asyncio.run(repository.put(artifact, b"1234567"))

    assert list(tmp_path.rglob("*.tmp")) == []
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == [
        tmp_path / "document-123" / "manifest" / "extract-v1"
    ]
