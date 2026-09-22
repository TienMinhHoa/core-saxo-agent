"""Infrastructure adapters for the ingestion ports."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import anyio

from saxophone.documents.policies import is_safe_document_reference
from saxophone.platform.concurrency import create_blocking_io_limiter
from saxophone.platform.model_client import (
    ModelClient,
    ModelRequest,
    ModelTask,
    ModelValidationError,
)

from .concept_records import ConceptVectorHit, ConceptVectorRecord
from .models import ChunkIndexRecord, EmbeddingRecord, IndexInputRecord, VectorHit
from .ports import ConceptVectorIndex, EmbeddingProvider, EmbeddingReuseStore, VectorIndex


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

    def __init__(
        self,
        path: str | Path,
        *,
        io_limiter: anyio.CapacityLimiter | None = None,
    ) -> None:
        self._path = Path(path)
        if self._path.name in {"", ".", ".."}:
            raise ValueError("embedding reuse store path must name a file")
        _reject_symbolic_link_in_path(self._path)
        self._lock_path = self._path.with_name(f".{self._path.name}.lock")
        self._io_limiter = io_limiter or create_blocking_io_limiter()

    @property
    def path(self) -> Path:
        """Path owned by this adapter, exposed for composition diagnostics."""
        return self._path

    async def find(self, records: Sequence[IndexInputRecord]) -> Mapping[str, ChunkIndexRecord]:
        requested = tuple(records)
        stored = await anyio.to_thread.run_sync(self._read, limiter=self._io_limiter)
        return {
            record.chunk_id: stored[key]
            for record in requested
            if (key := self._key(record)) in stored
        }

    async def save(self, records: Sequence[ChunkIndexRecord]) -> None:
        new_records = tuple(records)
        if not new_records:
            return
        await anyio.to_thread.run_sync(
            partial(self._save, new_records),
            limiter=self._io_limiter,
        )

    def _read(self) -> dict[tuple[str, str, str, str], ChunkIndexRecord]:
        with self._file_lock():
            return self._read_unlocked()

    def _read_unlocked(self) -> dict[tuple[str, str, str, str], ChunkIndexRecord]:
        _reject_symbolic_link_in_path(self._path)
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
        _reject_symbolic_link_in_path(self._path)
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
        _reject_symbolic_link_in_path(self._lock_path)
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


def _reject_symbolic_link_in_path(path: Path) -> None:
    """Reject a cache path whose existing components redirect persistence."""

    absolute_path = path.absolute()
    current = Path(absolute_path.anchor)
    for component in absolute_path.parts[1:]:
        current /= component
        if current.is_symlink():
            if current == absolute_path:
                raise ValueError("embedding reuse store path must not be a symbolic link")
            raise ValueError("embedding reuse store path must not contain a symbolic link")


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
        if isinstance(chunks, (str, bytes)) or not isinstance(chunks, Sequence):
            raise ValueError("chunks must be a sequence")
        chunk_ids = [chunk_id for chunk_id, _ in chunks]
        if any(not isinstance(chunk_id, str) or not chunk_id.strip() for chunk_id in chunk_ids):
            raise ValueError("chunk IDs must be non-blank strings")
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("chunk IDs must be unique")
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
            idempotency_key=_embedding_idempotency_key(chunks, source_version),
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
            if not vector or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in vector
            ):
                raise ModelValidationError("embedding vector values must be finite numbers")
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
        if len({record.dimension for record in records}) != 1:
            raise ModelValidationError("embedding vectors must have one shared dimension")
        return tuple(records)

    async def embed_texts(
        self,
        texts: Sequence[str],
    ) -> tuple[tuple[float, ...], ...]:
        """Expose the text-batch contract shared by concept and query flows."""

        if isinstance(texts, (str, bytes)) or not isinstance(texts, Sequence):
            raise ValueError("texts must be a sequence")
        normalized = tuple(texts)
        if any(not isinstance(text, str) or not text.strip() for text in normalized):
            raise ValueError("texts must contain non-blank strings")
        if not normalized:
            return ()
        serialized = json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        source_version = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        records = await self.embed(
            tuple((f"text-{index}", text) for index, text in enumerate(normalized)),
            source_version=f"text-batch-{source_version}",
        )
        return tuple(record.vector for record in records)


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic embedding provider for service and integration tests."""

    def __init__(
        self,
        vectors: Mapping[str, Sequence[float]],
        *,
        model: str = "fake-embedding",
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must not be empty")
        if not isinstance(vectors, Mapping):
            raise ValueError("vectors must be a mapping")
        normalized: dict[str, tuple[float, ...]] = {}
        for chunk_id, vector in vectors.items():
            if not isinstance(chunk_id, str) or not chunk_id.strip():
                raise ValueError("vector chunk IDs must be non-blank strings")
            if isinstance(vector, (str, bytes)) or not isinstance(vector, Sequence):
                raise ValueError("vectors must contain finite numeric sequences")
            values = tuple(vector)
            if not values or any(
                isinstance(item, bool)
                or not isinstance(item, (int, float))
                or not math.isfinite(item)
                for item in values
            ):
                raise ValueError("vectors must contain finite numeric sequences")
            normalized[chunk_id] = tuple(float(item) for item in values)
        self._vectors = normalized
        self._model = model.strip()

    @property
    def model(self) -> str:
        return self._model

    async def embed(
        self,
        chunks: Sequence[tuple[str, str]],
        *,
        source_version: str,
    ) -> tuple[EmbeddingRecord, ...]:
        if not isinstance(source_version, str) or not source_version.strip():
            raise ValueError("source_version must not be empty")
        if isinstance(chunks, (str, bytes)) or not isinstance(chunks, Sequence):
            raise ValueError("chunks must be a sequence")
        chunk_ids = [chunk_id for chunk_id, _ in chunks]
        if any(not isinstance(chunk_id, str) or not chunk_id.strip() for chunk_id in chunk_ids):
            raise ValueError("chunk IDs must be non-blank strings")
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("chunk IDs must be unique")
        records: list[EmbeddingRecord] = []
        for chunk_id in chunk_ids:
            vector = self._vectors.get(chunk_id)
            if vector is None:
                raise ValueError(f"missing vector for chunk {chunk_id}")
            records.append(
                EmbeddingRecord(
                    chunk_id=chunk_id,
                    source_version=source_version.strip(),
                    model_profile=self._model,
                    vector=vector,
                )
            )
        return tuple(records)


def _embedding_idempotency_key(
    chunks: Sequence[tuple[str, str]], source_version: str
) -> str:
    payload = "\n".join(
        (source_version, *(f"{chunk_id}:{text}" for chunk_id, text in chunks))
    )
    return f"embed-{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


class ChromaVectorIndex(VectorIndex, ConceptVectorIndex):
    """Async Chroma adapter; every blocking SDK call runs in a worker thread."""

    def __init__(
        self,
        collection: Any,
        *,
        client: Any | None = None,
        concept_collection: Any | None = None,
        io_limiter: Any | None = None,
        embedding_dimension: int | None = None,
    ) -> None:
        if client is not None and not callable(getattr(client, "close", None)):
            raise TypeError("client must expose a callable close method")
        self._collection = collection
        self._concept_collection = concept_collection
        self._client = client
        self._closed = False
        if embedding_dimension is not None and (
            isinstance(embedding_dimension, bool)
            or not isinstance(embedding_dimension, int)
            or embedding_dimension < 1
        ):
            raise ValueError("embedding_dimension must be a positive integer")
        self._io_limiter = io_limiter or create_blocking_io_limiter()
        self._embedding_dimension = embedding_dimension

    def close(self) -> None:
        """Release the Chroma client owned by the composition root, when present."""
        if self._closed or self._client is None:
            return
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
        self._closed = True

    async def aclose(self) -> None:
        """Close the Chroma client without blocking the application event loop."""

        if self._client is not None:
            await anyio.to_thread.run_sync(
                self.close,
                limiter=self._io_limiter,
            )

    async def list_chunk_ids(self, *, document_ref: str) -> tuple[str, ...]:
        validated_document_ref = _validated_document_ref(document_ref)
        result = await anyio.to_thread.run_sync(
            partial(self._collection.get, where={"document_ref": validated_document_ref}),
            limiter=self._io_limiter,
        )
        ids = result.get("ids") if isinstance(result, Mapping) else None
        if not isinstance(ids, list) or any(
            not isinstance(item, str) or not item.strip() for item in ids
        ):
            raise ValueError("Chroma result ids must be a list of non-blank strings")
        if len(ids) != len(set(ids)):
            raise ValueError("Chroma result ids must be unique")
        return tuple(ids)

    async def upsert_chunks(self, records: Sequence[ChunkIndexRecord]) -> None:
        if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
            raise ValueError("records must be a sequence of ChunkIndexRecord")
        if not records:
            return
        if any(not isinstance(record, ChunkIndexRecord) for record in records):
            raise ValueError("records must contain ChunkIndexRecord values")
        chunk_ids = [record.chunk_id for record in records]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("Chroma upsert chunk IDs must be unique")
        expected_dimension = records[0].dimension
        if any(record.dimension != expected_dimension for record in records[1:]):
            raise ValueError("Chroma upsert embeddings must have one shared dimension")
        if self._embedding_dimension is not None:
            invalid = next(
                (record for record in records if record.dimension != self._embedding_dimension),
                None,
            )
            if invalid is not None:
                raise ValueError(
                    "embedding dimension does not match the configured Chroma collection"
                )
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

    async def upsert_concepts(self, records: Sequence[ConceptVectorRecord]) -> None:
        """Upsert canonical concepts into the separately owned catalog collection."""
        if self._concept_collection is None:
            raise ValueError("concept_collection must be configured")
        if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
            raise ValueError("records must be a sequence of ConceptVectorRecord")
        if not records:
            return
        if any(not isinstance(record, ConceptVectorRecord) for record in records):
            raise ValueError("records must contain ConceptVectorRecord values")
        record_ids = [record.record_id for record in records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("Chroma upsert concept IDs must be unique")
        expected_dimension = records[0].embedding_dimensions
        if any(record.embedding_dimensions != expected_dimension for record in records[1:]):
            raise ValueError("Chroma upsert embeddings must have one shared dimension")
        if self._embedding_dimension is not None and expected_dimension != self._embedding_dimension:
            raise ValueError(
                "concept embedding dimension does not match the configured Chroma collection"
            )
        await anyio.to_thread.run_sync(
            partial(
                self._concept_collection.upsert,
                ids=record_ids,
                embeddings=[list(record.embedding) for record in records],
                documents=[record.search_text for record in records],
                metadatas=[self._concept_metadata(record) for record in records],
            ),
            limiter=self._io_limiter,
        )

    async def delete_concepts(self, record_ids: Sequence[str]) -> None:
        if self._concept_collection is None:
            raise ValueError("concept_collection must be configured")
        validated_ids = _validated_concept_ids(record_ids)
        if validated_ids:
            await anyio.to_thread.run_sync(
                partial(self._concept_collection.delete, ids=validated_ids),
                limiter=self._io_limiter,
            )

    async def query_concepts(
        self,
        query_vector: Sequence[float],
        *,
        limit: int = 10,
    ) -> list[ConceptVectorHit]:
        if self._concept_collection is None:
            raise ValueError("concept_collection must be configured")
        validated_limit = _validated_search_limit(limit)
        if validated_limit == 0:
            return []
        validated_vector = _validated_query_vector(
            query_vector,
            expected_dimension=self._embedding_dimension,
        )
        result = await anyio.to_thread.run_sync(
            partial(
                self._concept_collection.query,
                query_embeddings=[validated_vector],
                n_results=validated_limit,
                include=["documents", "metadatas", "distances"],
            ),
            limiter=self._io_limiter,
        )
        ids, documents, metadatas, distances = _validated_concept_rows(result)
        return [
            ConceptVectorHit(
                record_id=record_id,
                canonical_label=metadata["canonical_label"],
                normalized_label=metadata["normalized_label"],
                search_text=document,
                metadata=metadata,
                distance=distance,
            )
            for record_id, document, metadata, distance in zip(
                ids, documents, metadatas, distances
            )
        ]

    async def delete_chunks(self, chunk_ids: Sequence[str]) -> None:
        validated_ids = _validated_chunk_ids(chunk_ids)
        if validated_ids:
            await anyio.to_thread.run_sync(
                partial(self._collection.delete, ids=validated_ids),
                limiter=self._io_limiter,
            )

    async def search(
        self,
        query_vector: Sequence[float],
        *,
        filters: Mapping[str, object] | None = None,
        limit: int = 10,
    ) -> list[VectorHit]:
        validated_limit = _validated_search_limit(limit)
        if validated_limit == 0:
            return []
        validated_filters = _validated_search_filters(filters)
        validated_vector = _validated_query_vector(
            query_vector,
            expected_dimension=self._embedding_dimension,
        )
        result = await anyio.to_thread.run_sync(
            partial(
                self._collection.query,
            query_embeddings=[validated_vector],
            where=validated_filters,
            n_results=validated_limit,
            include=["documents", "metadatas", "distances"],
            ),
            limiter=self._io_limiter,
        )
        return self._hits(result)

    @staticmethod
    def _metadata(record: ChunkIndexRecord) -> dict[str, object]:
        reserved_keys = {
            "chunk_id",
            "document_ref",
            "source_version",
            "embedding_profile",
            "access_scope",
        }
        if reserved_keys.intersection(record.metadata):
            raise ValueError("Chroma metadata contains reserved keys")
        projected = {
            key: _chroma_metadata_value(value)
            for key, value in record.metadata.items()
        }
        if any(
            not isinstance(key, str) or not key.strip()
            for key in projected
        ):
            raise ValueError("Chroma metadata keys must be non-blank strings")
        if any(not _is_valid_chroma_metadata_value(value) for value in projected.values()):
            raise ValueError("Chroma metadata values must be finite scalar values or lists")
        return {
            "chunk_id": record.chunk_id,
            **projected,
            "document_ref": record.document_ref,
            "source_version": record.source_version,
            "embedding_profile": record.embedding_profile,
            "access_scope": record.access_scope,
        }

    @staticmethod
    def _concept_metadata(record: ConceptVectorRecord) -> dict[str, object]:
        required = {
            "canonical_label": record.canonical_label,
            "normalized_label": record.normalized_label,
            "usage_count": record.usage_count,
            "embedding_input_hash": record.embedding_input_hash,
            "embedding_model": record.embedding_model,
            "embedding_dimensions": record.embedding_dimensions,
            "index_version": record.index_version,
        }
        for key, expected in required.items():
            if key in record.metadata and record.metadata[key] != expected:
                raise ValueError(f"concept metadata {key} does not match record")
        extras = {
            key: _chroma_metadata_value(value)
            for key, value in record.metadata.items()
            if key not in required
        }
        if any(not isinstance(key, str) or not key.strip() for key in extras):
            raise ValueError("Chroma concept metadata keys must be non-blank strings")
        if any(not _is_valid_chroma_metadata_value(value) for value in extras.values()):
            raise ValueError(
                "Chroma concept metadata values must be finite scalar values or lists"
            )
        return {**required, **extras}

    @staticmethod
    def _hits(result: Any) -> list[VectorHit]:
        ids, documents, metadatas, distances = _validated_chroma_rows(result)
        return [
            VectorHit(
                chunk_id=chunk_id,
                document=document,
                metadata=metadata,
                distance=distance,
            )
            for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances)
        ]


def _chroma_metadata_value(value: object) -> object:
    """Project provider-independent tuple metadata into Chroma's list shape."""
    return _project_chroma_metadata_value(value, active_containers=set())


def _project_chroma_metadata_value(
    value: object, *, active_containers: set[int]
) -> object:
    """Project nested sequences while rejecting recursive metadata graphs."""
    if isinstance(value, (tuple, list)):
        container_id = id(value)
        if container_id in active_containers:
            raise ValueError("Chroma metadata values must not contain cycles")
        active_containers.add(container_id)
        try:
            return [
                _project_chroma_metadata_value(
                    item, active_containers=active_containers
                )
                for item in value
            ]
        finally:
            active_containers.remove(container_id)
    return value


def _is_valid_chroma_metadata_value(value: object) -> bool:
    if value is None or isinstance(value, (bytes, bytearray, Mapping)):
        return False
    if isinstance(value, bool) or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_valid_chroma_metadata_scalar(item) for item in value)
    return False


def _is_valid_chroma_metadata_scalar(value: object) -> bool:
    """Return whether a value is one Chroma-supported metadata list item."""
    if value is None or isinstance(value, (bytes, bytearray, Mapping, list)):
        return False
    if isinstance(value, bool) or isinstance(value, str):
        return True
    return isinstance(value, (int, float)) and math.isfinite(value)


def _validated_chroma_rows(
    result: Any,
) -> tuple[list[str], list[str], list[Mapping[str, object]], list[float]]:
    if not isinstance(result, Mapping):
        raise ValueError("Chroma result must be a mapping")
    rows: list[list[object]] = []
    for field in ("ids", "documents", "metadatas", "distances"):
        value = result.get(field)
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], list):
            raise ValueError(f"Chroma result {field} must be one nested list")
        rows.append(value[0])
    if len({len(row) for row in rows}) != 1:
        raise ValueError("Chroma result rows must have equal lengths")

    ids, documents, metadatas, distances = rows
    if any(not isinstance(item, str) or not item.strip() for item in ids):
        raise ValueError("Chroma result ids must be non-blank strings")
    if len(ids) != len(set(ids)):
        raise ValueError("Chroma result ids must be unique")
    if any(not isinstance(item, str) for item in documents):
        raise ValueError("Chroma result documents must contain strings")
    if any(not isinstance(item, Mapping) for item in metadatas):
        raise ValueError("Chroma result metadatas must contain mappings")
    if any(
        not _is_valid_chroma_metadata_mapping(item)
        for item in metadatas
    ):
        raise ValueError("Chroma result metadata must contain valid projections")
    for chunk_id, metadata in zip(ids, metadatas):
        metadata_chunk_id = metadata.get("chunk_id")
        if not isinstance(metadata_chunk_id, str) or not metadata_chunk_id.strip():
            raise ValueError("Chroma result metadata chunk_id must be a non-blank string")
        if metadata_chunk_id != chunk_id:
            raise ValueError("Chroma result metadata chunk_id must match result id")
        if not _has_valid_reserved_metadata(metadata):
            raise ValueError("Chroma result reserved metadata must be non-blank strings")
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(item)
        for item in distances
    ):
        raise ValueError("Chroma result distances must be finite numbers")
    if any(item < 0 for item in distances):
        raise ValueError("Chroma result distances must be non-negative")
    return ids, documents, metadatas, distances


def _has_valid_reserved_metadata(value: Mapping[object, object]) -> bool:
    """Reject malformed reserved identity fields returned by the provider."""
    reserved_keys = (
        "document_ref",
        "source_version",
        "embedding_profile",
        "access_scope",
    )
    return all(
        key not in value
        or isinstance(value[key], str) and bool(value[key].strip())
        for key in reserved_keys
    )


def _is_valid_chroma_metadata_mapping(value: Mapping[object, object]) -> bool:
    """Validate provider metadata before exposing it as a typed vector hit."""
    return (
        all(isinstance(key, str) and key.strip() for key in value)
        and all(_is_valid_chroma_metadata_value(item) for item in value.values())
    )


def _validated_chunk_ids(chunk_ids: Sequence[str]) -> list[str]:
    """Validate deletion IDs before allowing a destructive provider call."""
    if isinstance(chunk_ids, (str, bytes)) or not isinstance(chunk_ids, Sequence):
        raise ValueError("chunk_ids must be a sequence of non-blank strings")
    validated = list(chunk_ids)
    if any(not isinstance(item, str) or not item.strip() for item in validated):
        raise ValueError("chunk_ids must be a sequence of non-blank strings")
    if len(validated) != len(set(validated)):
        raise ValueError("Chroma delete chunk IDs must be unique")
    return validated


def _validated_concept_ids(record_ids: Sequence[str]) -> list[str]:
    """Validate stable catalog IDs before allowing destructive provider I/O."""
    if isinstance(record_ids, (str, bytes)) or not isinstance(record_ids, Sequence):
        raise ValueError("concept record IDs must be a sequence of stable IDs")
    validated = list(record_ids)
    if any(not isinstance(item, str) or not item.strip() for item in validated):
        raise ValueError("concept record IDs must be a sequence of stable IDs")
    if len(validated) != len(set(validated)):
        raise ValueError("Chroma delete concept IDs must be unique")
    if any(not _is_valid_concept_record_id(item) for item in validated):
        raise ValueError("concept record IDs must use concept::sha256 form")
    return validated


def _is_valid_concept_record_id(value: str) -> bool:
    digest = value.removeprefix("concept::")
    return (
        value.startswith("concept::")
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    )


def _validated_concept_rows(
    result: Any,
) -> tuple[list[str], list[str], list[Mapping[str, object]], list[float]]:
    if not isinstance(result, Mapping):
        raise ValueError("Chroma concept result must be a mapping")
    rows: list[list[object]] = []
    for field in ("ids", "documents", "metadatas", "distances"):
        value = result.get(field)
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], list):
            raise ValueError(f"Chroma concept result {field} must be one nested list")
        rows.append(value[0])
    if len({len(row) for row in rows}) != 1:
        raise ValueError("Chroma concept result rows must have equal lengths")

    ids, documents, metadatas, distances = rows
    if any(not isinstance(item, str) or not item.strip() for item in ids):
        raise ValueError("Chroma concept result IDs must be non-blank strings")
    if len(ids) != len(set(ids)):
        raise ValueError("Chroma concept result IDs must be unique")
    if any(not _is_valid_concept_record_id(item) for item in ids):
        raise ValueError("Chroma concept result IDs must use concept::sha256 form")
    if any(not isinstance(item, str) or not item.strip() for item in documents):
        raise ValueError("Chroma concept result documents must contain non-blank strings")
    if any(not isinstance(item, Mapping) for item in metadatas):
        raise ValueError("Chroma concept result metadata must contain mappings")
    if any(not _is_valid_chroma_metadata_mapping(item) for item in metadatas):
        raise ValueError("Chroma concept result metadata must contain valid projections")
    for record_id, metadata in zip(ids, metadatas):
        canonical_label = metadata.get("canonical_label")
        normalized_label = metadata.get("normalized_label")
        if not isinstance(canonical_label, str) or not canonical_label.strip():
            raise ValueError("Chroma concept metadata canonical_label must be non-blank")
        if not isinstance(normalized_label, str) or not normalized_label.strip():
            raise ValueError("Chroma concept metadata normalized_label must be non-blank")
        expected_id = f"concept::{hashlib.sha256(normalized_label.encode('utf-8')).hexdigest()}"
        if record_id != expected_id:
            raise ValueError("Chroma concept metadata normalized_label does not match result id")
        usage_count = metadata.get("usage_count")
        if isinstance(usage_count, bool) or not isinstance(usage_count, int) or usage_count < 0:
            raise ValueError("Chroma concept metadata usage_count must be non-negative")
        for field in ("embedding_input_hash", "embedding_model", "index_version"):
            value = metadata.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Chroma concept metadata {field} must be non-blank")
        embedding_dimensions = metadata.get("embedding_dimensions")
        if (
            isinstance(embedding_dimensions, bool)
            or not isinstance(embedding_dimensions, int)
            or embedding_dimensions < 1
        ):
            raise ValueError(
                "Chroma concept metadata embedding_dimensions must be positive"
            )
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(item)
        or item < 0
        for item in distances
    ):
        raise ValueError("Chroma concept result distances must be finite non-negative numbers")
    return ids, documents, metadatas, distances


def _validated_document_ref(document_ref: str) -> str:
    """Validate the reconcile scope before issuing a provider read."""
    if not is_safe_document_reference(document_ref):
        raise ValueError("document_ref must be a safe document reference")
    return document_ref


def _validated_query_vector(
    query_vector: Sequence[float], *, expected_dimension: int | None
) -> list[float]:
    if isinstance(query_vector, (str, bytes)) or not isinstance(query_vector, Sequence):
        raise ValueError("query_vector must be a non-empty sequence of finite numbers")
    validated = list(query_vector)
    if not validated or any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(item)
        for item in validated
    ):
        raise ValueError("query_vector must be a non-empty sequence of finite numbers")
    if expected_dimension is not None and len(validated) != expected_dimension:
        raise ValueError("query vector dimension does not match the configured Chroma collection")
    return [float(item) for item in validated]


def _validated_search_limit(limit: int) -> int:
    """Validate the provider row count without allowing bool or fractional values."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("limit must be a non-negative integer")
    return limit


def _validated_search_filters(
    filters: Mapping[str, object] | None,
) -> dict[str, object] | None:
    """Validate Chroma's scalar ``where`` projection before provider I/O."""
    if filters is None:
        return None
    if not isinstance(filters, Mapping):
        raise ValueError("filters must be a mapping of non-blank keys to scalar values")
    validated = dict(filters)
    if any(not isinstance(key, str) or not key.strip() for key in validated):
        raise ValueError("filters keys must be non-blank strings")
    if any(not _is_valid_chroma_metadata_scalar(value) for value in validated.values()):
        raise ValueError("filters values must be finite scalar values")
    return validated
