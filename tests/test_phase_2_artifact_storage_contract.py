from __future__ import annotations

import asyncio
import hashlib
import os
import threading
import time
from pathlib import Path

import anyio
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


@pytest.mark.parametrize("root", ["artifacts", None, 123])
def test_local_repository_rejects_non_path_root_before_storage_setup(
    root: object,
) -> None:
    with pytest.raises(ValueError, match="root must be a Path"):
        LocalArtifactRepository(root)  # type: ignore[arg-type]


def test_local_repository_rejects_existing_file_as_root(tmp_path: Path) -> None:
    root_file = tmp_path / "artifact-root"
    root_file.write_bytes(b"not-a-directory")

    with pytest.raises(ValueError, match="root must be a directory"):
        LocalArtifactRepository(root_file)


def test_local_repository_rejects_symbolic_link_as_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "artifact-root"
    root.mkdir()
    real_is_symlink = Path.is_symlink

    def pretend_symlink(path: Path) -> bool:
        return path == root or real_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", pretend_symlink)

    with pytest.raises(ValueError, match="root must not be a symbolic link"):
        LocalArtifactRepository(root)


def test_local_repository_rejects_symbolic_link_in_root_parent_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    symlink_parent = tmp_path / "shared-artifacts"
    root = symlink_parent / "artifact-root"
    real_is_symlink = Path.is_symlink

    def pretend_symlink(path: Path) -> bool:
        return path == symlink_parent or real_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", pretend_symlink)

    with pytest.raises(ValueError, match="root path must not contain a symbolic link"):
        LocalArtifactRepository(root)


@pytest.mark.parametrize("io_limiter", [object(), False, 1])
def test_local_repository_rejects_invalid_io_limiter_before_storage_setup(
    tmp_path: Path, io_limiter: object
) -> None:
    with pytest.raises(ValueError, match="io_limiter must be a CapacityLimiter"):
        LocalArtifactRepository(tmp_path, io_limiter=io_limiter)  # type: ignore[arg-type]


def test_local_repository_accepts_explicit_capacity_limiter(tmp_path: Path) -> None:
    limiter = anyio.CapacityLimiter(1)

    repository = LocalArtifactRepository(tmp_path, io_limiter=limiter)

    assert repository._io_limiter is limiter


def test_put_rejects_payload_that_does_not_match_declared_size_or_digest(
    tmp_path: Path,
) -> None:
    repository = LocalArtifactRepository(tmp_path)

    with pytest.raises(ValueError, match="size_bytes"):
        asyncio.run(repository.put(_artifact(), b"wrong"))

    with pytest.raises(ValueError, match="sha256"):
        asyncio.run(repository.put(_artifact(), b"7654321"))


@pytest.mark.parametrize("method", ["put", "get"])
def test_repository_rejects_non_artifact_reference_before_storage_io(
    tmp_path: Path, method: str
) -> None:
    repository = LocalArtifactRepository(tmp_path)

    with pytest.raises(ValueError, match="artifact must be an ArtifactRef"):
        if method == "put":
            asyncio.run(repository.put(object(), b"1234567"))  # type: ignore[arg-type]
        else:
            asyncio.run(repository.get(object()))  # type: ignore[arg-type]

    assert list(tmp_path.rglob("*")) == []


@pytest.mark.parametrize("payload", ["1234567", bytearray(b"1234567"), memoryview(b"1234567")])
def test_put_rejects_non_bytes_payload_before_storage_io(
    tmp_path: Path, payload: object
) -> None:
    repository = LocalArtifactRepository(tmp_path)

    with pytest.raises(ValueError, match="payload must be bytes"):
        asyncio.run(repository.put(_artifact(), payload))  # type: ignore[arg-type]

    assert list(tmp_path.rglob("*")) == []


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


def test_put_rejects_existing_directory_at_immutable_artifact_path(
    tmp_path: Path,
) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()
    destination = tmp_path / artifact.artifact_id / artifact.version
    destination.mkdir(parents=True)

    with pytest.raises(FileExistsError, match="immutable"):
        asyncio.run(repository.put(artifact, b"1234567"))

    assert destination.is_dir()
    assert list(tmp_path.rglob("*.tmp")) == []


def test_get_rejects_directory_at_immutable_artifact_path(
    tmp_path: Path,
) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()
    destination = tmp_path / artifact.artifact_id / artifact.version
    destination.mkdir(parents=True)

    with pytest.raises(FileExistsError, match="not a file"):
        asyncio.run(repository.get(artifact))


def test_get_raises_file_not_found_for_missing_artifact(tmp_path: Path) -> None:
    repository = LocalArtifactRepository(tmp_path)

    with pytest.raises(FileNotFoundError):
        asyncio.run(repository.get(_artifact()))


def test_get_performs_artifact_path_validation_inside_blocking_io_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = LocalArtifactRepository(tmp_path)
    caller_thread = threading.get_ident()
    observed_threads: list[int] = []
    real_path_for = repository._path_for

    def observe_path_for(artifact: ArtifactRef) -> Path:
        observed_threads.append(threading.get_ident())
        return real_path_for(artifact)

    monkeypatch.setattr(repository, "_path_for", observe_path_for)

    with pytest.raises(FileNotFoundError):
        asyncio.run(repository.get(_artifact()))

    assert observed_threads
    assert observed_threads == [thread_id for thread_id in observed_threads if thread_id != caller_thread]


def test_get_performs_payload_validation_inside_blocking_io_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()
    asyncio.run(repository.put(artifact, b"1234567"))
    caller_thread = threading.get_ident()
    observed_threads: list[int] = []
    real_validate_payload = repository._validate_payload

    def observe_validate_payload(artifact_ref: ArtifactRef, payload: bytes) -> None:
        observed_threads.append(threading.get_ident())
        real_validate_payload(artifact_ref, payload)

    monkeypatch.setattr(repository, "_validate_payload", observe_validate_payload)

    assert asyncio.run(repository.get(artifact)) == b"1234567"

    assert observed_threads
    assert observed_threads == [
        thread_id for thread_id in observed_threads if thread_id != caller_thread
    ]


def test_put_performs_payload_validation_inside_blocking_io_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()
    caller_thread = threading.get_ident()
    observed_threads: list[int] = []
    real_validate_payload = repository._validate_payload

    def observe_validate_payload(artifact_ref: ArtifactRef, payload: bytes) -> None:
        observed_threads.append(threading.get_ident())
        real_validate_payload(artifact_ref, payload)

    monkeypatch.setattr(repository, "_validate_payload", observe_validate_payload)

    asyncio.run(repository.put(artifact, b"1234567"))

    assert observed_threads
    assert observed_threads == [thread_id for thread_id in observed_threads if thread_id != caller_thread]


def test_repository_rejects_symbolic_link_at_artifact_identity(
    tmp_path: Path,
) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()
    destination = tmp_path / "document-123" / "manifest" / "extract-v1"
    target = tmp_path / "other-artifact"
    target.write_bytes(b"1234567")
    destination.parent.mkdir(parents=True)
    try:
        destination.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symbolic links unavailable: {exc}")

    with pytest.raises(FileExistsError, match="symbolic link"):
        asyncio.run(repository.get(artifact))

    with pytest.raises(FileExistsError, match="symbolic link"):
        asyncio.run(repository.put(artifact, b"1234567"))


def test_repository_symbolic_link_guard_is_fail_closed_without_link_privilege(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()
    destination = tmp_path / "document-123" / "manifest" / "extract-v1"
    real_is_symlink = Path.is_symlink

    def pretend_symlink(path: Path) -> bool:
        return path == destination or real_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", pretend_symlink)

    with pytest.raises(FileExistsError, match="symbolic link"):
        asyncio.run(repository.get(artifact))

    with pytest.raises(FileExistsError, match="symbolic link"):
        asyncio.run(repository.put(artifact, b"1234567"))

    assert list(tmp_path.rglob("*")) == []


def test_repository_rejects_symbolic_link_in_artifact_parent_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()
    parent = tmp_path / "document-123" / "manifest"
    real_is_symlink = Path.is_symlink

    def pretend_symlink(path: Path) -> bool:
        return path == parent or real_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", pretend_symlink)

    with pytest.raises(FileExistsError, match="symbolic link"):
        asyncio.run(repository.put(artifact, b"1234567"))

    assert list(tmp_path.rglob("*")) == []


def test_repository_checks_artifact_components_before_resolving_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()
    parent = tmp_path / "document-123" / "manifest"
    real_is_symlink = Path.is_symlink
    real_resolve = Path.resolve

    def pretend_symlink(path: Path) -> bool:
        return path == parent or real_is_symlink(path)

    def reject_resolution_of_artifact_path(path: Path, *args: object, **kwargs: object) -> Path:
        if path != tmp_path:
            raise AssertionError("artifact path was resolved before symlink validation")
        return real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "is_symlink", pretend_symlink)
    monkeypatch.setattr(Path, "resolve", reject_resolution_of_artifact_path)

    with pytest.raises(FileExistsError, match="symbolic link"):
        asyncio.run(repository.put(artifact, b"1234567"))

    assert list(tmp_path.rglob("*")) == []


def test_repository_rechecks_root_symbolic_link_before_artifact_path_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()
    real_is_symlink = Path.is_symlink

    def pretend_symlink(path: Path) -> bool:
        return path == tmp_path or real_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", pretend_symlink)

    with pytest.raises(ValueError, match="root must not be a symbolic link"):
        asyncio.run(repository.put(artifact, b"1234567"))

    assert list(tmp_path.rglob("*")) == []


def test_repository_rechecks_artifact_parent_after_directory_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()
    parent = tmp_path / "document-123" / "manifest"
    real_mkdir = Path.mkdir
    real_is_symlink = Path.is_symlink
    parent_created = False

    def create_parent_then_report_symlink(
        path: Path, *args: object, **kwargs: object
    ) -> None:
        nonlocal parent_created
        real_mkdir(path, *args, **kwargs)
        if path == parent:
            parent_created = True

    def report_symlink_after_creation(path: Path) -> bool:
        return (path == parent and parent_created) or real_is_symlink(path)

    monkeypatch.setattr(Path, "mkdir", create_parent_then_report_symlink)
    monkeypatch.setattr(Path, "is_symlink", report_symlink_after_creation)

    with pytest.raises(FileExistsError, match="symbolic link"):
        asyncio.run(repository.put(artifact, b"1234567"))

    assert list(tmp_path.rglob("*.tmp")) == []
    assert not (parent / artifact.version).exists()


def test_atomic_commit_does_not_replace_file_created_after_existence_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()
    destination = tmp_path / "document-123" / "manifest" / "extract-v1"
    real_link = os.link

    def create_competing_file_then_link(source: str, target: str) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"external")
        real_link(source, target)

    monkeypatch.setattr(
        "saxophone.platform.artifacts.os.link", create_competing_file_then_link
    )

    with pytest.raises(FileExistsError):
        asyncio.run(repository.put(artifact, b"1234567"))

    assert destination.read_bytes() == b"external"
    assert list(tmp_path.rglob("*.tmp")) == []


def test_atomic_commit_cleans_temporary_file_when_publish_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = LocalArtifactRepository(tmp_path)
    artifact = _artifact()

    def fail_publish(source: str, target: str) -> None:
        raise OSError("simulated publish failure")

    monkeypatch.setattr("saxophone.platform.artifacts.os.link", fail_publish)

    with pytest.raises(OSError, match="simulated publish failure"):
        asyncio.run(repository.put(artifact, b"1234567"))

    assert list(tmp_path.rglob("*.tmp")) == []
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == []


def test_concurrent_puts_cannot_replace_the_same_immutable_artifact(
    tmp_path: Path,
) -> None:
    repository = LocalArtifactRepository(tmp_path)
    first = _artifact()
    replacement = ArtifactRef(
        artifact_id=first.artifact_id,
        version=first.version,
        kind=first.kind,
        media_type=first.media_type,
        sha256=hashlib.sha256(b"7654321").hexdigest(),
        size_bytes=7,
    )

    async def write_both() -> list[BaseException | None]:
        results = await asyncio.gather(
            repository.put(first, b"1234567"),
            repository.put(replacement, b"7654321"),
            return_exceptions=True,
        )
        return results

    results = asyncio.run(write_both())

    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, FileExistsError) for result in results) == 1
    assert asyncio.run(repository.get(first)) == b"1234567"


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
