"""Application ports for retrieval infrastructure."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Mapping, Sequence

from .models import ChunkHit


class ChunkRetriever(ABC):
    """Async retrieval port hiding vector, lexical, and provider details."""

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        filters: Mapping[str, object] | None = None,
        limit: int = 10,
    ) -> Sequence[ChunkHit]:
        raise NotImplementedError
