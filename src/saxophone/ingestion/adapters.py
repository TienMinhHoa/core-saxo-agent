"""Infrastructure adapters for the ingestion ports."""

from __future__ import annotations

from functools import partial
from typing import Any, Mapping, Sequence

import anyio

from .models import ChunkIndexRecord, VectorHit
from .ports import VectorIndex


class ChromaVectorIndex(VectorIndex):
    """Async Chroma adapter; every blocking SDK call runs in a worker thread."""

    def __init__(self, collection: Any) -> None:
        self._collection = collection

    async def upsert_chunks(self, records: Sequence[ChunkIndexRecord]) -> None:
        if not records:
            return
        await anyio.to_thread.run_sync(
            partial(
                self._collection.upsert,
            ids=[record.chunk_id for record in records],
            embeddings=[list(record.embedding) for record in records],
            documents=[record.search_text for record in records],
            metadatas=[self._metadata(record) for record in records],
            )
        )

    async def delete_chunks(self, chunk_ids: Sequence[str]) -> None:
        if chunk_ids:
            await anyio.to_thread.run_sync(
                partial(self._collection.delete, ids=list(chunk_ids))
            )

    async def search(
        self,
        query_vector: Sequence[float],
        *,
        filters: Mapping[str, object] | None = None,
        limit: int = 10,
    ) -> list[VectorHit]:
        if limit < 1:
            return []
        result = await anyio.to_thread.run_sync(
            partial(
                self._collection.query,
            query_embeddings=[list(query_vector)],
            where=filters,
            n_results=limit,
            include=["documents", "metadatas", "distances"],
            )
        )
        return self._hits(result)

    @staticmethod
    def _metadata(record: ChunkIndexRecord) -> dict[str, object]:
        return {
            **dict(record.metadata),
            "document_ref": record.document_ref,
            "source_version": record.source_version,
            "embedding_profile": record.embedding_profile,
            "access_scope": record.access_scope,
        }

    @staticmethod
    def _hits(result: Any) -> list[VectorHit]:
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        return [
            VectorHit(
                chunk_id=chunk_id,
                document=document or "",
                metadata=metadata or {},
                distance=distance,
            )
            for chunk_id, document, metadata, distance in zip(
                ids, documents, metadatas, distances
            )
        ]
