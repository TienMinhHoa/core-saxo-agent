"""Infrastructure adapters for the ingestion ports."""

from __future__ import annotations

from functools import partial
from typing import Any, Mapping, Sequence

import anyio

from saxophone.platform.model_client import (
    ModelClient,
    ModelRequest,
    ModelTask,
    ModelValidationError,
)

from .models import ChunkIndexRecord, EmbeddingRecord, VectorHit
from .ports import EmbeddingProvider, VectorIndex


class RemoteEmbeddingProvider(EmbeddingProvider):
    """Map a typed EMBED response without exposing model transport to ingestion."""

    def __init__(self, client: ModelClient, *, model: str) -> None:
        if not model.strip():
            raise ValueError("model must not be empty")
        self._client = client
        self._model = model.strip()

    @property
    def model(self) -> str:
        """Configured remote model profile, exposed for composition diagnostics."""
        return self._model

    async def embed(
        self,
        chunks: Sequence[tuple[str, str]],
        *,
        source_version: str,
    ) -> tuple[EmbeddingRecord, ...]:
        if not source_version.strip():
            raise ValueError("source_version must not be empty")
        request = ModelRequest(
            model=self._model,
            task=ModelTask.EMBED,
            input={
                "texts": [
                    {"chunk_id": chunk_id, "text": text}
                    for chunk_id, text in chunks
                ]
            },
            metadata={"source_version": source_version},
            response_schema="embedding-v1",
        )
        response = await self._client.invoke(request)
        if response.task is not ModelTask.EMBED:
            raise ModelValidationError("embedding response task is invalid")
        if response.response_schema != "embedding-v1":
            raise ModelValidationError("embedding response schema is invalid")
        if response.source_version != source_version:
            raise ModelValidationError("embedding response source_version is invalid")
        raw_embeddings = response.output.get("embeddings")
        if not isinstance(raw_embeddings, list):
            raise ModelValidationError("embedding response embeddings must be a list")
        expected_ids = [chunk_id for chunk_id, _ in chunks]
        actual_ids: list[str] = []
        records: list[EmbeddingRecord] = []
        for item in raw_embeddings:
            if not isinstance(item, dict):
                raise ModelValidationError("embedding item must be a mapping")
            chunk_id = item.get("chunk_id")
            vector = item.get("vector")
            if not isinstance(chunk_id, str) or not chunk_id.strip():
                raise ModelValidationError("embedding chunk_id is invalid")
            if not isinstance(vector, list):
                raise ModelValidationError("embedding vector must be a list")
            actual_ids.append(chunk_id)
            records.append(
                EmbeddingRecord(
                    chunk_id=chunk_id,
                    source_version=source_version,
                    model_profile=self._model,
                    vector=tuple(vector),
                )
            )
        if actual_ids != expected_ids:
            raise ModelValidationError("embedding response chunk IDs do not match request")
        return tuple(records)


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
