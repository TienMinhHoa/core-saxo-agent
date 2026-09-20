"""Infrastructure adapters for the provider-independent retrieval port."""

from __future__ import annotations

from functools import partial
import asyncio
import math
import re
import unicodedata
from collections.abc import Sequence
from typing import Any, Mapping

import anyio

from music_rag.semantic import semantic_search
from music_rag.store import CatalogStore
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
        _require_canonical_version(retrieval_version)
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
        ids, documents, metadatas, distances = _validated_chroma_rows(result)
        hits: list[ChunkHit] = []
        for rank, chunk_id in enumerate(ids, start=1):
            metadata = metadatas[rank - 1] if rank - 1 < len(metadatas) else {}
            document = documents[rank - 1] if rank - 1 < len(documents) else ""
            distance = distances[rank - 1] if rank - 1 < len(distances) else None
            if not isinstance(chunk_id, str) or not chunk_id.strip():
                raise ValueError("Chroma result chunk ids must be non-blank strings")
            normalized_metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
            if isinstance(document, str) and document:
                normalized_metadata["document"] = document
            score = 1.0 - distance if distance is not None else None
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


class LegacySemanticRetriever(ChunkRetriever):
    """Expose the legacy catalog search through the async retrieval port.

    This is a compatibility adapter, not a second application contract.  It
    keeps the legacy catalog alive during migration while callers depend only
    on ``ChunkHit`` and can later switch to a native semantic adapter.
    """

    def __init__(
        self,
        store: CatalogStore,
        embedding_provider: Any,
        *,
        retrieval_version: str = "legacy-semantic-v1",
        io_limiter: Any | None = None,
    ) -> None:
        if not retrieval_version.strip():
            raise ValueError("retrieval_version must not be blank")
        self._store = store
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
        access_scope = (filters or {}).get("access_scope")
        if not isinstance(access_scope, str) or not access_scope.strip():
            raise ValueError("access_scope filter is required")
        unsupported = set(filters or {}) - {"access_scope"}
        if unsupported:
            raise ValueError(f"unsupported legacy filters: {sorted(unsupported)}")
        records = await anyio.to_thread.run_sync(
            partial(
                semantic_search,
                self._store,
                self._embedding_provider,
                query.strip(),
                access_scope,
                limit,
            ),
            limiter=self._io_limiter,
        )
        return [self._map_record(record, rank) for rank, record in enumerate(records, start=1)]

    def _map_record(self, record: Mapping[str, Any], rank: int) -> ChunkHit:
        document_ref = f"{record['document_id']}:{record['source_version']}"
        chunk_ref = str(record["search_unit_id"])
        metadata = dict(record)
        metadata.pop("score", None)
        metadata.pop("semantic_score", None)
        metadata.pop("keyword_score", None)
        return ChunkHit(
            document_ref,
            chunk_ref,
            rank,
            self._retrieval_version,
            metadata,
            semantic_score=float(record["semantic_score"]),
            keyword_score=float(record["keyword_score"]),
        )


class InMemoryLexicalRetriever(ChunkRetriever):
    """Small provider-independent lexical adapter for header/content/tag search."""

    def __init__(
        self,
        records: Sequence[ChunkHit],
        *,
        retrieval_version: str = "lexical-v1",
    ) -> None:
        if not retrieval_version.strip():
            raise ValueError("retrieval_version must not be blank")
        self._records = tuple(records)
        self._retrieval_version = retrieval_version

    async def search(
        self,
        query: str,
        *,
        filters: Mapping[str, object] | None = None,
        limit: int = 10,
    ) -> list[ChunkHit]:
        if limit < 1:
            return []
        terms = _terms(query)
        if not terms:
            raise ValueError("query must not be blank")
        ranked: list[tuple[float, ChunkHit]] = []
        for record in self._records:
            if not _matches_filters(record, filters):
                continue
            haystack = " ".join(_metadata_text(record.metadata)).lower()
            matched = sum(term in haystack for term in terms)
            if not matched:
                continue
            score = matched / len(terms)
            ranked.append(
                (
                    score,
                    ChunkHit(
                        record.source_ref,
                        record.chunk_ref,
                        1,
                        self._retrieval_version,
                        record.metadata,
                        keyword_score=score,
                    ),
                )
            )
        ranked.sort(key=lambda item: (-item[0], item[1].chunk_ref))
        return [
            ChunkHit(
                hit.source_ref,
                hit.chunk_ref,
                rank,
                hit.retrieval_version,
                hit.metadata,
                keyword_score=hit.keyword_score,
            )
            for rank, (_, hit) in enumerate(ranked[:limit], start=1)
        ]


class HybridRetriever(ChunkRetriever):
    """Fuse semantic and lexical rankings with Reciprocal Rank Fusion."""

    def __init__(
        self,
        semantic: ChunkRetriever,
        lexical: ChunkRetriever,
        *,
        rrf_k: int = 60,
        retrieval_version: str = "hybrid-v1",
    ) -> None:
        if rrf_k < 1:
            raise ValueError("rrf_k must be at least 1")
        if not retrieval_version.strip():
            raise ValueError("retrieval_version must not be blank")
        self._semantic = semantic
        self._lexical = lexical
        self._rrf_k = rrf_k
        self._retrieval_version = retrieval_version

    async def search(
        self,
        query: str,
        *,
        filters: Mapping[str, object] | None = None,
        limit: int = 10,
    ) -> list[ChunkHit]:
        if limit < 1:
            return []
        semantic_hits, lexical_hits = await asyncio.gather(
            self._semantic.search(query, filters=filters, limit=limit),
            self._lexical.search(query, filters=filters, limit=limit),
        )
        merged: dict[str, dict[str, object]] = {}
        for hits, score_name in ((semantic_hits, "semantic_score"), (lexical_hits, "keyword_score")):
            for hit in hits:
                item = merged.setdefault(hit.chunk_ref, {"hit": hit, "fused": 0.0})
                item["fused"] = float(item["fused"]) + 1 / (self._rrf_k + hit.rank)
                if score_name == "semantic_score":
                    item["semantic"] = hit.semantic_score
                else:
                    item["keyword"] = hit.keyword_score
        ordered = sorted(
            merged.values(), key=lambda item: (-float(item["fused"]), str(item["hit"].chunk_ref))
        )
        results: list[ChunkHit] = []
        for rank, item in enumerate(ordered[:limit], start=1):
            hit = item["hit"]
            results.append(
                ChunkHit(
                    hit.source_ref,
                    hit.chunk_ref,
                    rank,
                    self._retrieval_version,
                    hit.metadata,
                    semantic_score=item.get("semantic"),
                    keyword_score=item.get("keyword"),
                    fused_score=float(item["fused"]),
                )
            )
        return results


def _validated_chroma_rows(
    result: Mapping[str, Any],
) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
    if not isinstance(result, Mapping):
        raise ValueError("Chroma result must be a mapping")
    rows: list[list[Any]] = []
    for field in ("ids", "documents", "metadatas", "distances"):
        value = result.get(field)
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], list):
            raise ValueError(f"Chroma result field {field!r} must contain one row")
        rows.append(value[0])
    ids, documents, metadatas, distances = rows
    expected = len(ids)
    if any(len(row) != expected for row in (documents, metadatas, distances)):
        raise ValueError("Chroma result fields must have matching row lengths")
    for distance in distances:
        if distance is not None and (
            isinstance(distance, bool)
            or not isinstance(distance, (int, float))
            or not math.isfinite(distance)
        ):
            raise ValueError("Chroma result distances must be finite numbers")
    return ids, documents, metadatas, distances


def _require_canonical_version(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("retrieval_version must not be blank")
    if value != value.strip() or unicodedata.normalize("NFC", value) != value:
        raise ValueError("retrieval_version must contain a canonical value")


def _terms(query: str) -> tuple[str, ...]:
    if not isinstance(query, str) or not query.strip():
        return ()
    return tuple(dict.fromkeys(re.findall(r"[\w-]+", query.lower())))


def _metadata_text(metadata: Mapping[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    for value in metadata.values():
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (list, tuple, set)):
            values.extend(item for item in value if isinstance(item, str))
    return tuple(values)


def _matches_filters(hit: ChunkHit, filters: Mapping[str, object] | None) -> bool:
    return all(hit.metadata.get(key) == value for key, value in (filters or {}).items())
