"""Local filesystem adapter for immutable, versioned artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from saxophone.documents.models import ArtifactRef


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


def _is_safe_image_reference(image_ref: object) -> bool:
    if not isinstance(image_ref, str) or not image_ref.strip():
        return False
    candidate = image_ref.strip().replace("\\", "/")
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc or candidate.startswith("/"):
        return False
    return ".." not in Path(candidate).parts


class LocalArtifactRepository:
    """Persist artifacts outside the event loop using atomic replacement."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    async def put(self, artifact: ArtifactRef, payload: bytes) -> None:
        self._validate_payload(artifact, payload)
        await asyncio.to_thread(self._write_atomically, artifact, payload)

    async def get(self, artifact: ArtifactRef) -> bytes:
        path = self._path_for(artifact)
        return await asyncio.to_thread(path.read_bytes)

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
        if len(payload) != artifact.size_bytes:
            raise ValueError("payload size_bytes does not match artifact metadata")
        digest = hashlib.sha256(payload).hexdigest()
        if digest != artifact.sha256:
            raise ValueError("payload sha256 does not match artifact metadata")
