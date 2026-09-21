"""Pure policies used by the legacy UI callbacks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def select_chroma_records(response: object) -> list[dict[str, object]]:
    """Extract mapping records from a validated Chroma response shape."""
    if not isinstance(response, Mapping):
        return []
    items = response.get("items")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes, bytearray)):
        return []
    return [
        record
        for item in items
        if isinstance(item, Mapping)
        and isinstance(record := item.get("record"), dict)
    ]


def select_answer_records(
    response: object,
    final_hits: Sequence[object],
    *,
    max_final_hits: int = 3,
) -> list[dict[str, object]]:
    """Select unique evidence, preferring agent-selected response items."""
    if not isinstance(response, Mapping) or not isinstance(max_final_hits, int) or max_final_hits < 0:
        return []

    records: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    items = response.get("items")
    if isinstance(items, Sequence) and not isinstance(items, (str, bytes, bytearray)):
        candidates: Sequence[object] = items
    else:
        candidates = ()
    for item in candidates:
        record = item.get("record") if isinstance(item, Mapping) else None
        if isinstance(record, dict) and isinstance(record.get("chunk_id"), str):
            chunk_id = record["chunk_id"]
            if chunk_id not in seen_ids:
                records.append(record)
                seen_ids.add(chunk_id)

    for record in final_hits[:max_final_hits]:
        if isinstance(record, dict) and isinstance(record.get("chunk_id"), str):
            chunk_id = record["chunk_id"]
            if chunk_id not in seen_ids:
                records.append(record)
                seen_ids.add(chunk_id)
    return records
