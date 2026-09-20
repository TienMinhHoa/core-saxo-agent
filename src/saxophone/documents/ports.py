"""Application ports for document-owned persistence."""

from __future__ import annotations

from typing import Protocol

from saxophone.documents.knowledge import KnowledgeChunk
from saxophone.documents.models import ArtifactRef
from saxophone.ingestion.models import EmbeddingRecord


class ArtifactRepository(Protocol):
    """Store and retrieve immutable artifact bytes by their typed identity."""

    async def put(self, artifact: ArtifactRef, payload: bytes) -> None:
        """Persist an artifact, validating its declared size and checksum."""

    async def get(self, artifact: ArtifactRef) -> bytes:
        """Return the artifact bytes or raise FileNotFoundError."""


class KnowledgeRepository(Protocol):
    """Persist full-fidelity chunk metadata independently of vector search."""

    async def upsert(self, chunk: KnowledgeChunk) -> None:
        """Create or replace one chunk by its stable identifier."""

    async def get(self, chunk_id: str) -> KnowledgeChunk:
        """Return a chunk or raise FileNotFoundError."""

    async def delete(self, chunk_id: str) -> None:
        """Delete a chunk or raise FileNotFoundError."""


class VectorIndex(Protocol):
    """Index vectors without exposing Chroma or another SDK to use cases."""

    async def upsert(self, records: tuple[EmbeddingRecord, ...]) -> None:
        """Atomically upsert one validated embedding batch."""

    async def delete(self, chunk_ids: tuple[str, ...]) -> None:
        """Remove indexed chunks by stable identity."""
