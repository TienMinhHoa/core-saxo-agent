"""Infrastructure adapters for the ingestion ports."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import anyio

from saxophone.platform.concurrency import create_blocking_io_limiter
from saxophone.platform.model_client import (
    ModelClient,
    ModelRequest,
    ModelTask,
    ModelValidationError,
)

from .models import ChunkIndexRecord, EmbeddingRecord, IndexInputRecord, VectorHit
from .ports import EmbeddingProvider, EmbeddingReuseStore, VectorIndex


class InMemoryEmbeddingReuseStore(EmbeddingReuseStore):
    """Process-local cache keyed by the exact source projection and model profile."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str, str], ChunkIndexRecord] = {}

    async def find(self, records: Sequence[IndexInputRecord]) -> Mapping[str, ChunkIndexRecord]:
        return {
            record.chunk_id: self._records[key]
            for record in records
            if (key := self._key(record)) in self._records
        }

    async def save(self, records: Sequence[ChunkIndexRecord]) -> None:
        for record in records:
            self._records[self._key(record)] = record

    @staticmethod
    def _key(record: IndexInputRecord | ChunkIndexRecord) -> tuple[str, str, str, str]:
        return (
            record.chunk_id,
            record.source_version,
            record.embedding_profile,
            record.search_text,
        )


class FileEmbeddingReuseStore(EmbeddingReuseStore):
    """Durable embedding cache with atomic replacement and process locking.

    The file stores only validated ``ChunkIndexRecord`` projections. A missing
    file means an empty cache; malformed persisted data fails loudly so a
    corrupted cache cannot silently change indexing behavior.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        if self._path.name in {"", ".", ".."}:
            raise ValueError("embedding reuse store path must name a file")
        self._lock_path = self._path.with_name(f".{self._path.name}.lock")

    @property
    def path(self) -> Path:
        """Path owned by this adapter, exposed for composition diagnostics."""
        return self._path

    async def find(self, records: Sequence[IndexInputRecord]) -> Mapping[str, ChunkIndexRecord]:
        requested = tuple(records)
        stored = await anyio.to_thread.run_sync(self._read)
        return {
            record.chunk_id: stored[key]
            for record in requested
            if (key := self._key(record)) in stored
        }

    async def save(self, records: Sequence[ChunkIndexRecord]) -> None:
        new_records = tuple(records)
        if not new_records:
            return
        await anyio.to_thread.run_sync(partial(self._save, new_records))

    def _read(self) -> dict[tuple[str, str, str, str], ChunkIndexRecord]:
        with self._file_lock():
            return self._read_unlocked()

    def _read_unlocked(self) -> dict[tuple[str, str, str, str], ChunkIndexRecord]:
        if not self._path.exists():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError("payload must be a list")
            records = [self._decode(item) for item in payload]
        except (KeyError, OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise ValueError(f"embedding reuse store is corrupt: {self._path}") from error
        return {self._key(record): record for record in records}

    def _save(self, records: Sequence[ChunkIndexRecord]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._file_lock():
            merged = self._read_unlocked()
            for record in records:
                merged[self._key(record)] = record
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{self._path.name}.", suffix=".tmp", dir=self._path.parent
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as temporary:
                    json.dump(
                        [self._encode(record) for record in merged.values()],
                        temporary,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_name, self._path)
            except BaseException:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass
                raise

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        """Serialize read-modify-write cycles across processes."""
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a+b") as lock_file:
            lock_file.seek(0)
            lock_file.write(b"0")
            lock_file.flush()
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _key(record: IndexInputRecord | ChunkIndexRecord) -> tuple[str, str, str, str]:
        return (
            record.chunk_id,
            record.source_version,
            record.embedding_profile,
            record.search_text,
        )

    @staticmethod
    def _encode(record: ChunkIndexRecord) -> dict[str, object]:
        return {
            "chunk_id": record.chunk_id,
            "document_ref": record.document_ref,
            "source_version": record.source_version,
            "search_text": record.search_text,
            "embedding": list(record.embedding),
            "embedding_profile": record.embedding_profile,
            "access_scope": record.access_scope,
            "metadata": dict(record.metadata),
        }

    @staticmethod
    def _decode(item: object) -> ChunkIndexRecord:
        if not isinstance(item, dict):
            raise ValueError("record must be a mapping")
        embedding = item.get("embedding")
        metadata = item.get("metadata")
        if not isinstance(embedding, list) or not isinstance(metadata, dict):
            raise ValueError("record embedding and metadata are invalid")
        return ChunkIndexRecord(
            chunk_id=item["chunk_id"],
            document_ref=item["document_ref"],
            source_version=item["source_version"],
            search_text=item["search_text"],
            embedding=tuple(embedding),
            embedding_profile=item["embedding_profile"],
            access_scope=item["access_scope"],
            metadata=metadata,
        )


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

    def __init__(self, collection: Any, *, io_limiter: Any | None = None) -> None:
        self._collection = collection
        self._io_limiter = io_limiter or create_blocking_io_limiter()

    async def list_chunk_ids(self, *, document_ref: str) -> tuple[str, ...]:
        result = await anyio.to_thread.run_sync(
            partial(self._collection.get, where={"document_ref": document_ref}),
            limiter=self._io_limiter,
        )
        ids = result.get("ids") if isinstance(result, Mapping) else None
        if not isinstance(ids, list):
            return ()
        return tuple(item for item in ids if isinstance(item, str) and item.strip())

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
            ),
            limiter=self._io_limiter,
        )

    async def delete_chunks(self, chunk_ids: Sequence[str]) -> None:
        if chunk_ids:
            await anyio.to_thread.run_sync(
                partial(self._collection.delete, ids=list(chunk_ids)),
                limiter=self._io_limiter,
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
