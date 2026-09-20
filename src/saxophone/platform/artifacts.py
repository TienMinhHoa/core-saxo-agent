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
        self._root = root.resolve()
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
        if not path.exists():
            raise FileNotFoundError(path)
        if not path.is_file():
            raise FileExistsError("artifact identity is not a file")
        return path.read_bytes()

    def _path_for(self, artifact: ArtifactRef) -> Path:
        relative = Path(artifact.artifact_id) / artifact.version
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("artifact_id must stay within the artifact root")
        path = (self._root / relative).resolve()
        if path != self._root and self._root not in path.parents:
            raise ValueError("artifact_id must stay within the artifact root")
        return path

    def _write_atomically(self, artifact: ArtifactRef, payload: bytes) -> None:
        with self._write_lock:
            path = self._path_for(artifact)
            path.parent.mkdir(parents=True, exist_ok=True)
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
