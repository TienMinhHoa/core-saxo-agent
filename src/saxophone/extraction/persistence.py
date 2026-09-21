"""Persistence use case for immutable extraction output artifacts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from saxophone.documents import ArtifactRef, ArtifactRepository

from .models import PdfExtractionResult


class PersistExtractionArtifacts:
    """Validate and persist all output artifacts from one extraction result.

    Payload transfer is deliberately supplied by the caller.  The use case
    owns completeness and integrity checks, while the repository owns storage
    mechanics and atomic replacement of each immutable artifact.
    """

    _OUTPUT_NAMES = ("markdown", "layout", "manifest")

    def __init__(self, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def execute(
        self,
        result: PdfExtractionResult,
        payloads: Mapping[str, bytes],
    ) -> PdfExtractionResult:
        self._validate_payload_set(result, payloads)
        for name in self._OUTPUT_NAMES:
            await self._artifacts.put(getattr(result, name), payloads[name])
        return result

    @classmethod
    def _validate_payload_set(
        cls,
        result: PdfExtractionResult,
        payloads: Mapping[str, bytes],
    ) -> None:
        if not isinstance(payloads, Mapping):
            raise ValueError("extraction payloads must be a mapping")
        missing = [name for name in cls._OUTPUT_NAMES if name not in payloads]
        if missing:
            raise ValueError(f"missing extraction payload: {missing[0]}")
        for name in cls._OUTPUT_NAMES:
            artifact: ArtifactRef = getattr(result, name)
            payload = payloads[name]
            if not isinstance(payload, bytes):
                raise ValueError(f"extraction payload {name} must be bytes")
            if len(payload) != artifact.size_bytes:
                raise ValueError(f"extraction payload {name} size mismatch")
            if hashlib.sha256(payload).hexdigest() != artifact.sha256:
                raise ValueError(f"extraction payload {name} checksum mismatch")


class RepositoryExtractionArtifactPayloadProvider:
    """Load extraction outputs from the backend-owned artifact repository."""

    _OUTPUT_NAMES = ("markdown", "layout", "manifest")

    def __init__(self, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def fetch(self, result: PdfExtractionResult) -> dict[str, bytes]:
        return {
            name: await self._artifacts.get(getattr(result, name))
            for name in self._OUTPUT_NAMES
        }
