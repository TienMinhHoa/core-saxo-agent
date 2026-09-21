"""Local filesystem adapter for immutable, versioned artifacts."""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from pathlib import Path

import anyio

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.documents.policies import (
    is_image_media_type,
    is_safe_relative_image_reference,
)
from saxophone.documents.ports import ArtifactRepository, ImageArtifactResolver
from saxophone.platform.concurrency import create_blocking_io_limiter


class SafeImageArtifactGate:
    """Allow only backend-owned relative image references."""

    async def validate(self, image_refs: tuple[str, ...]) -> tuple[str, ...]:
        validated: list[str] = []
        for image_ref in image_refs:
            if not is_safe_relative_image_reference(image_ref):
                raise ValueError("unsafe image reference")
            if image_ref not in validated:
                validated.append(image_ref)
        return tuple(validated)


class RepositoryBackedImageArtifactGate:
    """Validate image references and verify their immutable repository bytes."""

    def __init__(
        self, repository: ArtifactRepository, resolver: ImageArtifactResolver
    ) -> None:
        self._repository = repository
        self._resolver = resolver
        self._safe_gate = SafeImageArtifactGate()

    async def validate(self, image_refs: tuple[str, ...]) -> tuple[str, ...]:
        safe_refs = await self._safe_gate.validate(image_refs)
        for image_ref in safe_refs:
            artifact = await self._resolver.resolve(image_ref)
            if artifact.kind is not ArtifactKind.IMAGE:
                raise ValueError("resolved artifact kind must be IMAGE")
            if not is_image_media_type(artifact.media_type):
                raise ValueError("resolved image artifact must have an image media type")
            payload = await self._repository.get(artifact)
            _validate_payload(artifact, payload)
        return safe_refs


class LocalArtifactRepository:
    """Persist artifacts outside the event loop using atomic replacement."""

    def __init__(
        self,
        root: Path,
        *,
        io_limiter: anyio.CapacityLimiter | None = None,
    ) -> None:
        if not isinstance(root, Path):
            raise ValueError("root must be a Path")
        if io_limiter is not None and not isinstance(io_limiter, anyio.CapacityLimiter):
            raise ValueError("io_limiter must be a CapacityLimiter")
        _reject_symbolic_link_in_path(root)
        resolved_root = root.resolve()
        if resolved_root.exists() and not resolved_root.is_dir():
            raise ValueError("root must be a directory")
        self._root = resolved_root
        self._io_limiter = io_limiter or create_blocking_io_limiter()
        self._write_lock = threading.Lock()

    async def put(self, artifact: ArtifactRef, payload: bytes) -> None:
        _require_artifact_ref(artifact)
        self._validate_payload(artifact, payload)
        await anyio.to_thread.run_sync(
            self._write_atomically,
            artifact,
            payload,
            limiter=self._io_limiter,
        )

    async def get(self, artifact: ArtifactRef) -> bytes:
        _require_artifact_ref(artifact)
        path = self._path_for(artifact)
        payload = await anyio.to_thread.run_sync(
            self._read_file,
            path,
            limiter=self._io_limiter,
        )
        self._validate_payload(artifact, payload)
        return payload

    @staticmethod
    def _read_file(path: Path) -> bytes:
        if path.is_symlink():
            raise FileExistsError("artifact identity must not be a symbolic link")
        if not path.exists():
            raise FileNotFoundError(path)
        if not path.is_file():
            raise FileExistsError("artifact identity is not a file")
        return path.read_bytes()

    def _path_for(self, artifact: ArtifactRef) -> Path:
        _reject_symbolic_link_in_path(self._root)
        relative = Path(artifact.artifact_id) / artifact.version
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("artifact_id must stay within the artifact root")
        path = self._root / relative
        current = self._root
        for component in relative.parts:
            current /= component
            if current.is_symlink():
                raise FileExistsError("artifact path must not contain a symbolic link")
        resolved = path.resolve()
        if resolved != self._root and self._root not in resolved.parents:
            raise ValueError("artifact_id must stay within the artifact root")
        return path

    def _write_atomically(self, artifact: ArtifactRef, payload: bytes) -> None:
        with self._write_lock:
            path = self._path_for(artifact)
            if path.is_symlink():
                raise FileExistsError("artifact identity must not be a symbolic link")
            path.parent.mkdir(parents=True, exist_ok=True)
            # Directory creation can follow a parent symlink introduced after
            # the first path validation; revalidate before opening a temp file.
            path = self._path_for(artifact)
            if path.exists():
                if not path.is_file():
                    raise FileExistsError("artifact identity is immutable")
                if path.read_bytes() == payload:
                    return
                raise FileExistsError("artifact identity is immutable")
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
            )
            try:
                with os.fdopen(fd, "wb") as temporary:
                    temporary.write(payload)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                # Linking a fully flushed temporary file publishes it atomically
                # without replacing a destination created by another writer.
                os.link(temporary_name, path)
            except BaseException:
                Path(temporary_name).unlink(missing_ok=True)
                raise
            else:
                Path(temporary_name).unlink(missing_ok=True)

    @staticmethod
    def _validate_payload(artifact: ArtifactRef, payload: bytes) -> None:
        _validate_payload(artifact, payload)


def _validate_payload(artifact: ArtifactRef, payload: bytes) -> None:
    if not isinstance(payload, bytes):
        raise ValueError("payload must be bytes")
    if len(payload) != artifact.size_bytes:
        raise ValueError("payload size_bytes does not match artifact metadata")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != artifact.sha256:
        raise ValueError("payload sha256 does not match artifact metadata")


def _require_artifact_ref(artifact: object) -> None:
    if not isinstance(artifact, ArtifactRef):
        raise ValueError("artifact must be an ArtifactRef")


def _reject_symbolic_link_in_path(path: Path) -> None:
    """Reject a root whose explicit path crosses a symbolic-link component."""
    absolute_path = path.absolute()
    current = Path(absolute_path.anchor)
    for component in absolute_path.parts[1:]:
        current /= component
        if current.is_symlink():
            if current == absolute_path:
                raise ValueError("root must not be a symbolic link")
            raise ValueError("root path must not contain a symbolic link")
