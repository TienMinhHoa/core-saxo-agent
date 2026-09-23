"""Application ports for ingestion infrastructure."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Mapping, Sequence

from .concept_records import ConceptVectorHit, ConceptVectorRecord
from .models import ChunkIndexRecord, EmbeddingRecord, IndexInputRecord, VectorHit


@dataclass(frozen=True, slots=True)
class VectorCollectionSummary:
    """Safe collection metadata exposed by the read-only database browser."""

    name: str
    count: int


@dataclass(frozen=True, slots=True)
class VectorRecord:
    """One Chroma record without its potentially large embedding vector."""

    record_id: str
    document: str
    metadata: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class VectorRecordPage:
    """A bounded page returned by the vector database browser port."""

    collection_name: str
    offset: int
    limit: int
    total_count: int
    records: tuple[VectorRecord, ...]
    has_more: bool


class VectorDatabaseBrowser(ABC):
    """Read-only administrative view over configured vector collections."""

    @abstractmethod
    async def list_collections(self) -> tuple[VectorCollectionSummary, ...]:
        raise NotImplementedError

    @abstractmethod
    async def get_records(
        self,
        collection_name: str,
        *,
        offset: int,
        limit: int,
        query: str | None,
        document_ref: str | None,
    ) -> VectorRecordPage:
        raise NotImplementedError


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

    @abstractmethod
    async def delete_concepts(self, record_ids: Sequence[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def query_concepts(
        self,
        query_vector: Sequence[float],
        *,
        limit: int = 10,
    ) -> list[ConceptVectorHit]:
        raise NotImplementedError
