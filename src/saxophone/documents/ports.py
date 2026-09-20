"""Application ports for document-owned persistence."""

from __future__ import annotations

from typing import Protocol

from saxophone.documents.models import ArtifactRef


class ArtifactRepository(Protocol):
    """Store and retrieve immutable artifact bytes by their typed identity."""

    async def put(self, artifact: ArtifactRef, payload: bytes) -> None:
        """Persist an artifact, validating its declared size and checksum."""

    async def get(self, artifact: ArtifactRef) -> bytes:
        """Return the artifact bytes or raise FileNotFoundError."""
