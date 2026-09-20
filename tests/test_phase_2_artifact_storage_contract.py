from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from pathlib import Path

import pytest

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.documents.ports import ArtifactRepository
from saxophone.platform.artifacts import LocalArtifactRepository
from saxophone.platform.concurrency import create_blocking_io_limiter


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


def test_repository_does_not_allow_artifact_id_path_traversal() -> None:
    with pytest.raises(ValueError, match="artifact_id"):
        _artifact(artifact_id="../outside")


def test_put_is_atomic_and_does_not_leave_temporary_files(tmp_path: Path) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()

    asyncio.run(repository.put(artifact, b"1234567"))

    assert list(tmp_path.rglob("*.tmp")) == []
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == [
        tmp_path / "document-123" / "manifest" / "extract-v1"
    ]


def test_get_rejects_tampered_payload_against_immutable_metadata(tmp_path: Path) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()

    asyncio.run(repository.put(artifact, b"1234567"))
    (tmp_path / "document-123" / "manifest" / "extract-v1").write_bytes(
        b"tampered"
    )

    with pytest.raises(ValueError, match="size_bytes|sha256"):
        asyncio.run(repository.get(artifact))


def test_put_is_idempotent_for_same_bytes_but_rejects_replacement(tmp_path: Path) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()
    replacement = ArtifactRef(
        artifact_id=artifact.artifact_id,
        version=artifact.version,
        kind=artifact.kind,
        media_type=artifact.media_type,
        sha256=hashlib.sha256(b"7654321").hexdigest(),
        size_bytes=7,
    )

    asyncio.run(repository.put(artifact, b"1234567"))
    asyncio.run(repository.put(artifact, b"1234567"))

    with pytest.raises(FileExistsError, match="immutable"):
        asyncio.run(repository.put(replacement, b"7654321"))


def test_local_repository_bounds_concurrent_blocking_writes(tmp_path: Path) -> None:
    repository = LocalArtifactRepository(
        tmp_path,
        io_limiter=create_blocking_io_limiter(1),
    )
    artifacts = [
        _artifact(artifact_id=f"document-{index}/manifest")
        for index in (1, 2)
    ]
    active = 0
    peak = 0
    lock = threading.Lock()
    release = threading.Event()

    def blocking_write(artifact: ArtifactRef, payload: bytes) -> None:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        release.wait(timeout=2)
        with lock:
            active -= 1

    repository._write_atomically = blocking_write  # type: ignore[method-assign]

    async def run_writes() -> None:
        tasks = [
            asyncio.create_task(repository.put(artifact, b"1234567"))
            for artifact in artifacts
        ]
        for _ in range(20):
            await asyncio.sleep(0.01)
            with lock:
                if active == 1:
                    break
        release.set()
        await asyncio.gather(*tasks)

    asyncio.run(run_writes())

    assert peak == 1
