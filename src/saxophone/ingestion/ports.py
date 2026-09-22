"""Application ports for ingestion infrastructure."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Mapping, Sequence

from .concept_records import ConceptVectorRecord
from .models import ChunkIndexRecord, EmbeddingRecord, IndexInputRecord, VectorHit


class EmbeddingReuseStore(ABC):
    """Async port for reusing vectors whose source projection is unchanged."""

    @abstractmethod
    async def find(self, records: Sequence[IndexInputRecord]) -> Mapping[str, ChunkIndexRecord]:
        raise NotImplementedError

    @abstractmethod
    async def save(self, records: Sequence[ChunkIndexRecord]) -> None:
        raise NotImplementedError


class EmbeddingProvider(ABC):
    """Async port for vectors produced by the external model service."""

    @abstractmethod
    async def embed(
        self,
        chunks: Sequence[tuple[str, str]],
        *,
        source_version: str,
    ) -> tuple[EmbeddingRecord, ...]:
        raise NotImplementedError


class VectorIndex(ABC):
    """Async port hiding the blocking vector database client."""

    @abstractmethod
    async def list_chunk_ids(self, *, document_ref: str) -> tuple[str, ...]:
        """Return the currently indexed chunk IDs for one document."""
        raise NotImplementedError

    @abstractmethod
    async def upsert_chunks(self, records: Sequence[ChunkIndexRecord]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_chunks(self, chunk_ids: Sequence[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def search(
        self,
        query_vector: Sequence[float],
        *,
        filters: Mapping[str, object] | None = None,
        limit: int = 10,
    ) -> list[VectorHit]:
        raise NotImplementedError


class ConceptVectorIndex(ABC):
    """Async port for the canonical concept catalog collection."""

    @abstractmethod
    async def upsert_concepts(self, records: Sequence[ConceptVectorRecord]) -> None:
        raise NotImplementedError
