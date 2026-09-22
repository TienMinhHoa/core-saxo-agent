"""Deterministic vector outbox projections for embedded chunk records."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from saxophone.tagging.vector_outbox import VectorOutboxEvent

from .models import ChunkIndexRecord


def build_chunk_vector_upsert_event(
    record: ChunkIndexRecord,
    *,
    index_version: str,
    ingestion_run_id: str | None = None,
) -> VectorOutboxEvent:
    """Project one validated chunk record into an idempotent upsert event."""

    if not isinstance(record, ChunkIndexRecord):
        raise TypeError("record must be a ChunkIndexRecord")
    _require_non_blank("index_version", index_version)
    _validate_optional_scope("ingestion_run_id", ingestion_run_id)

    payload = {"record": _chunk_record_payload(record)}
    payload_json = _dump_json(payload)
    identity = _dump_json(
        {
            "collection": "document_chunks",
            "ingestion_run_id": ingestion_run_id,
            "index_version": index_version.strip(),
            "operation": "upsert",
            "payload": payload,
        }
    )
    event_id = f"chunk-upsert-{_sha256(identity)}"
    return VectorOutboxEvent(
        event_id=event_id,
        document_ref=record.document_ref,
        source_version=record.source_version,
        collection="document_chunks",
        record_id=record.chunk_id,
        operation="upsert",
        payload_json=payload_json,
        ingestion_run_id=ingestion_run_id,
        index_version=index_version.strip(),
    )


def build_chunk_vector_upsert_events(
    records: Sequence[ChunkIndexRecord],
    *,
    index_version: str,
    ingestion_run_id: str | None = None,
) -> tuple[VectorOutboxEvent, ...]:
    """Build stable events for one document-scoped batch of chunk records."""

    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise TypeError("records must be a sequence of ChunkIndexRecord values")
    _require_non_blank("index_version", index_version)
    _validate_optional_scope("ingestion_run_id", ingestion_run_id)
    normalized = tuple(records)
    if any(not isinstance(record, ChunkIndexRecord) for record in normalized):
        raise TypeError("records must contain ChunkIndexRecord values")
    chunk_ids = tuple(record.chunk_id for record in normalized)
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("chunk records must have unique chunk IDs")
    if normalized:
        document_refs = {record.document_ref for record in normalized}
        source_versions = {record.source_version for record in normalized}
        if len(document_refs) != 1:
            raise ValueError("chunk records must belong to the same document")
        if len(source_versions) != 1:
            raise ValueError("chunk records must use the same source version")
    events = (
        build_chunk_vector_upsert_event(
            record,
            index_version=index_version,
            ingestion_run_id=ingestion_run_id,
        )
        for record in sorted(normalized, key=lambda item: item.chunk_id)
    )
    return tuple(events)


def _chunk_record_payload(record: ChunkIndexRecord) -> dict[str, Any]:
    return {
        "access_scope": record.access_scope,
        "chunk_id": record.chunk_id,
        "document_ref": record.document_ref,
        "embedding": list(record.embedding),
        "embedding_profile": record.embedding_profile,
        "metadata": _json_value(record.metadata),
        "search_text": record.search_text,
        "source_version": record.source_version,
    }


def _json_value(value: object) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("chunk metadata must contain finite numbers")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValueError("chunk metadata must use string keys")
            normalized[key] = _json_value(nested)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise ValueError("chunk metadata must be JSON-compatible")


def _dump_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as error:
        raise ValueError("chunk vector event payload must be JSON-compatible") from error


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_non_blank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")


def _validate_optional_scope(name: str, value: str | None) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{name} must be blank or null")
