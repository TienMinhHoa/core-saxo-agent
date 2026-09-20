"""Application ports for ingestion infrastructure."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Mapping, Sequence

from .models import ChunkIndexRecord, VectorHit


class VectorIndex(ABC):
    """Async port hiding the blocking vector database client."""

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
