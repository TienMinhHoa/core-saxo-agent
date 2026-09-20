"""Infrastructure adapters for the provider-independent retrieval port."""

from __future__ import annotations

from functools import partial
from typing import Any, Mapping

import anyio

from saxophone.platform.concurrency import create_blocking_io_limiter
from .models import ChunkHit
from .ports import ChunkRetriever


class ChromaSemanticRetriever(ChunkRetriever):
    """Map blocking Chroma semantic search into the async retrieval contract."""

    def __init__(
        self,
        collection: Any,
        embedding_provider: Any,
        *,
        retrieval_version: str = "chroma-v1",
        io_limiter: Any | None = None,
    ) -> None:
        if not isinstance(retrieval_version, str) or not retrieval_version.strip():
            raise ValueError("retrieval_version must not be blank")
        self._collection = collection
        self._embedding_provider = embedding_provider
        self._retrieval_version = retrieval_version
        self._io_limiter = io_limiter or create_blocking_io_limiter()

    async def search(
        self,
        query: str,
        *,
        filters: Mapping[str, object] | None = None,
        limit: int = 10,
    ) -> list[ChunkHit]:
        if limit < 1:
            return []
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be blank")

        vectors = await anyio.to_thread.run_sync(
            partial(self._embedding_provider.embed, [query.strip()]),
            limiter=self._io_limiter,
        )
        if not vectors:
            return []
        result = await anyio.to_thread.run_sync(
            partial(
                self._collection.query,
                query_embeddings=[vectors[0]],
                where=dict(filters or {}),
                n_results=limit,
                include=["documents", "metadatas", "distances"],
            ),
            limiter=self._io_limiter,
        )
        return self._map_hits(result)

    def _map_hits(self, result: Mapping[str, Any]) -> list[ChunkHit]:
        ids = _first_result_list(result.get("ids"))
        documents = _first_result_list(result.get("documents"))
        metadatas = _first_result_list(result.get("metadatas"))
        distances = _first_result_list(result.get("distances"))
        hits: list[ChunkHit] = []
        for rank, chunk_id in enumerate(ids, start=1):
            metadata = metadatas[rank - 1] if rank - 1 < len(metadatas) else {}
            document = documents[rank - 1] if rank - 1 < len(documents) else ""
            distance = distances[rank - 1] if rank - 1 < len(distances) else None
            if not isinstance(chunk_id, str) or not chunk_id.strip():
                continue
            normalized_metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
            if isinstance(document, str) and document:
                normalized_metadata["document"] = document
            score = 1.0 - float(distance) if distance is not None else None
            hits.append(
                ChunkHit(
                    str(
                        normalized_metadata.get("document_ref")
                        or normalized_metadata.get("source_chunks")
                        or "chroma"
                    ),
                    chunk_id,
                    rank,
                    self._retrieval_version,
                    normalized_metadata,
                    semantic_score=score,
                )
            )
        return hits


def _first_result_list(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []
