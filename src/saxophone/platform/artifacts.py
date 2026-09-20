"""Local filesystem adapter for immutable, versioned artifacts."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import anyio

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.documents.ports import ArtifactRepository, ImageArtifactResolver
from saxophone.platform.concurrency import create_blocking_io_limiter


class SafeImageArtifactGate:
    """Allow only backend-owned relative image references."""

    async def validate(self, image_refs: tuple[str, ...]) -> tuple[str, ...]:
        validated: list[str] = []
        for image_ref in image_refs:
            if not _is_safe_image_reference(image_ref):
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
            payload = await self._repository.get(artifact)
            _validate_payload(artifact, payload)
        return safe_refs


def _is_safe_image_reference(image_ref: object) -> bool:
    if not isinstance(image_ref, str) or not image_ref.strip():
        return False
    candidate = image_ref.strip().replace("\\", "/")
    if candidate != image_ref:
        return False
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc or candidate.startswith("/"):
        return False
    path = Path(candidate)
    if ".." in path.parts:
        return False
    # Keep one canonical relative spelling so equivalent paths cannot bypass
    # asset allowlists or create duplicate cache keys.
    return path.as_posix() == candidate


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

    async def put(self, artifact: ArtifactRef, payload: bytes) -> None:
        self._validate_payload(artifact, payload)
        await anyio.to_thread.run_sync(
            self._write_atomically,
            artifact,
            payload,
            limiter=self._io_limiter,
        )

    async def get(self, artifact: ArtifactRef) -> bytes:
        path = self._path_for(artifact)
        payload = await anyio.to_thread.run_sync(
            path.read_bytes,
            limiter=self._io_limiter,
        )
        self._validate_payload(artifact, payload)
        return payload

    def _path_for(self, artifact: ArtifactRef) -> Path:
        relative = Path(artifact.artifact_id) / artifact.version
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("artifact_id must stay within the artifact root")
        path = (self._root / relative).resolve()
        if path != self._root and self._root not in path.parents:
            raise ValueError("artifact_id must stay within the artifact root")
        return path

    def _write_atomically(self, artifact: ArtifactRef, payload: bytes) -> None:
        path = self._path_for(artifact)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
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
            os.replace(temporary_name, path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise

    @staticmethod
    def _validate_payload(artifact: ArtifactRef, payload: bytes) -> None:
        _validate_payload(artifact, payload)


def _validate_payload(artifact: ArtifactRef, payload: bytes) -> None:
    if len(payload) != artifact.size_bytes:
        raise ValueError("payload size_bytes does not match artifact metadata")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != artifact.sha256:
        raise ValueError("payload sha256 does not match artifact metadata")
