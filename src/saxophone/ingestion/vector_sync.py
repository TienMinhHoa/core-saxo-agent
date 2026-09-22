"""Application service for draining durable vector outbox events."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Protocol

from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository, VectorOutboxEvent

from .concept_records import ConceptVectorRecord
from .models import ChunkIndexRecord
from .vector_state import VectorIndexState, build_chunk_vector_states


class _VectorIndex(Protocol):
    async def upsert_chunks(self, records: tuple[ChunkIndexRecord, ...]) -> None: ...

    async def delete_chunks(self, chunk_ids: tuple[str, ...]) -> None: ...

    async def upsert_concepts(self, records: tuple[ConceptVectorRecord, ...]) -> None: ...

    async def delete_concepts(self, record_ids: tuple[str, ...]) -> None: ...


class _VectorIndexState(Protocol):
    async def mark_synced(self, state: VectorIndexState) -> VectorIndexState: ...

    async def remove_record(
        self,
        *,
        collection_name: str,
        chroma_record_id: str,
        document_ref: str | None = None,
        index_version: str | None = None,
    ) -> None: ...


class VectorSyncService:
    """Apply pending/failed events and persist success or retry state per event."""

    def __init__(
        self,
        outbox: SqliteVectorOutboxRepository,
        vector_index: _VectorIndex,
        *,
        state: _VectorIndexState | None = None,
    ) -> None:
        if not callable(getattr(outbox, "list_pending", None)):
            raise TypeError("outbox must provide list_pending")
        if not callable(getattr(vector_index, "upsert_chunks", None)):
            raise TypeError("vector_index must provide upsert_chunks")
        if not callable(getattr(vector_index, "delete_chunks", None)):
            raise TypeError("vector_index must provide delete_chunks")
        if state is not None:
            if not callable(getattr(state, "mark_synced", None)):
                raise TypeError("state must provide mark_synced")
            if not callable(getattr(state, "remove_record", None)):
                raise TypeError("state must provide remove_record")
        self._outbox = outbox
        self._vector_index = vector_index
        self._state = state

    async def sync_pending(
        self,
        *,
        ingestion_run_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, int]:
        events = await self._outbox.list_pending(
            ingestion_run_id=ingestion_run_id,
            limit=limit,
        )
        succeeded = failed = 0
        for event in events:
            try:
                state = await self._apply(event)
                if self._state is not None:
                    if event.operation == "delete":
                        await self._state.remove_record(
                            collection_name=event.collection,
                            chroma_record_id=event.record_id,
                            document_ref=event.document_ref,
                            index_version=event.index_version,
                        )
                    elif state is not None:
                        await self._state.mark_synced(state)
            except Exception as error:
                await self._outbox.mark_failed(event.event_id, str(error) or type(error).__name__)
                failed += 1
            else:
                await self._outbox.mark_succeeded(event.event_id)
                succeeded += 1
        return {"succeeded": succeeded, "failed": failed}

    async def pending_count(self, *, ingestion_run_id: str | None = None) -> int:
        """Return retryable events left after a scoped synchronization attempt."""
        return await self._outbox.count_pending(ingestion_run_id=ingestion_run_id)

    async def _apply(self, event: VectorOutboxEvent) -> VectorIndexState | None:
        if event.collection == "concept_catalog":
            return await self._apply_concept(event)
        if event.collection != "document_chunks":
            raise ValueError("unsupported vector collection")
        if event.operation == "delete":
            await self._vector_index.delete_chunks((event.record_id,))
            return None
        try:
            payload = json.loads(event.payload_json)
            record_payload = payload["record"]
            if not isinstance(record_payload, Mapping):
                raise ValueError
            record = ChunkIndexRecord(
                chunk_id=record_payload["chunk_id"],
                document_ref=record_payload["document_ref"],
                source_version=record_payload["source_version"],
                search_text=record_payload["search_text"],
                embedding=tuple(record_payload["embedding"]),
                embedding_profile=record_payload["embedding_profile"],
                access_scope=record_payload["access_scope"],
                metadata=record_payload["metadata"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("vector upsert payload is invalid") from error
        if record.chunk_id != event.record_id or record.document_ref != event.document_ref:
            raise ValueError("vector upsert payload identity does not match event")
        await self._vector_index.upsert_chunks((record,))
        return _chunk_state(event, record)

    async def _apply_concept(self, event: VectorOutboxEvent) -> VectorIndexState | None:
        if event.operation == "delete":
            delete_concepts = getattr(self._vector_index, "delete_concepts", None)
            if not callable(delete_concepts):
                raise TypeError("vector_index must provide delete_concepts")
            await delete_concepts((event.record_id,))
            return None
        try:
            payload = json.loads(event.payload_json)
            record_payload = payload["record"]
            if not isinstance(record_payload, Mapping):
                raise ValueError
            record = ConceptVectorRecord(
                record_id=record_payload["record_id"],
                canonical_label=record_payload["canonical_label"],
                normalized_label=record_payload["normalized_label"],
                search_text=record_payload["search_text"],
                embedding=tuple(record_payload["embedding"]),
                usage_count=record_payload["usage_count"],
                embedding_input_hash=record_payload["embedding_input_hash"],
                embedding_model=record_payload["embedding_model"],
                embedding_dimensions=record_payload["embedding_dimensions"],
                index_version=record_payload["index_version"],
                metadata=record_payload["metadata"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("vector concept upsert payload is invalid") from error
        if record.record_id != event.record_id:
            raise ValueError("vector upsert payload identity does not match event")
        upsert_concepts = getattr(self._vector_index, "upsert_concepts", None)
        if not callable(upsert_concepts):
            raise TypeError("vector_index must provide upsert_concepts")
        await upsert_concepts((record,))
        return _concept_state(event, record)


def _chunk_state(event: VectorOutboxEvent, record: ChunkIndexRecord) -> VectorIndexState:
    index_version = event.index_version or _metadata_index_version(
        record.metadata, event.source_version
    )
    return build_chunk_vector_states((record,), index_version=index_version)[0]


def _concept_state(event: VectorOutboxEvent, record: ConceptVectorRecord) -> VectorIndexState:
    return VectorIndexState(
        entity_type="concept",
        entity_key=record.canonical_label,
        collection_name=event.collection,
        chroma_record_id=record.record_id,
        embedding_input_hash=record.embedding_input_hash,
        embedding_model=record.embedding_model,
        embedding_dimensions=record.embedding_dimensions,
        index_version=record.index_version,
        document_ref=event.document_ref,
        source_version=event.source_version,
    )


def _metadata_index_version(metadata: Mapping[str, object], fallback: str) -> str:
    value = metadata.get("index_version")
    return value.strip() if isinstance(value, str) and value.strip() else fallback
