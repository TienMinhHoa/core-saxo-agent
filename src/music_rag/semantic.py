"""Versioned, approved-only semantic retrieval over source-linked units."""
from __future__ import annotations

import math
from typing import Any

from .embeddings import EmbeddingProvider
from .store import CatalogStore
from .util import normalise_for_search, tokens


def _cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0


def _source_chunks(catalog: dict[str, Any], item: dict[str, Any], maximum_chars: int = 6_000) -> list[tuple[str, list[str]]]:
    """Chunk the *search representation*, retaining each block as evidence."""
    section = catalog["sections"].get(item["section_id"], {})
    prefix = section.get("title_raw", "")
    chunks: list[tuple[str, list[str]]] = []
    current = [prefix]
    evidence: list[str] = []
    for block_id in item["content_block_ids"]:
        block = catalog["blocks"][block_id]
        if block["kind"] == "asset":
            continue
        value = block["raw_text"]
        if evidence and len("\n".join(current)) + len(value) > maximum_chars:
            chunks.append((normalise_for_search("\n".join(current)), evidence))
            current, evidence = [prefix], []
        current.append(value)
        evidence.append(block_id)
    if evidence:
        chunks.append((normalise_for_search("\n".join(current)), evidence))
    return chunks


def build_semantic_index(store: CatalogStore, provider: EmbeddingProvider, *, batch_size: int = 32) -> dict[str, int | str]:
    catalog = store.load()
    pending: list[dict[str, Any]] = []
    skipped = 0
    for item in catalog["items"].values():
        document = catalog["documents"].get(f"{item['document_id']}:{item['source_version']}")
        if item.get("review_status") != "approved" or document is None:
            skipped += 1
            continue
        for sequence, (search_text, evidence) in enumerate(_source_chunks(catalog, item), start=1):
            pending.append({
                "search_unit_id": f"semantic_{item['item_id']}:{item['item_version']}:{sequence}",
                "item_id": item["item_id"], "item_version": item["item_version"],
                "document_id": item["document_id"], "source_version": item["source_version"],
                "search_text": search_text, "evidence_block_ids": evidence, "evidence_scope": "item",
            })
    units: list[dict[str, Any]] = []
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset : offset + batch_size]
        vectors = provider.embed([entry["search_text"] for entry in batch])
        if len(vectors) != len(batch):
            raise ValueError("embedding_response_count_mismatch")
        for entry, vector in zip(batch, vectors):
            units.append({**entry, "embedding": vector})
    catalog["semantic_index"] = {"provider_model": provider.model, "units": units}
    store.save(catalog)
    return {"indexed": len(units), "skipped_items": skipped, "model": provider.model}


def semantic_search(store: CatalogStore, provider: EmbeddingProvider, query: str, access_scope: str, limit: int = 10) -> list[dict[str, Any]]:
    catalog = store.load()
    index = catalog.get("semantic_index", {})
    if index.get("provider_model") != provider.model:
        raise ValueError("semantic_index_missing_or_model_mismatch")
    query_vector = provider.embed([query])[0]
    query_tokens = tokens(query)
    by_item: dict[tuple[str, int], dict[str, Any]] = {}
    for unit in index.get("units", []):
        item = catalog["items"].get(f"{unit['item_id']}:{unit['item_version']}")
        document = catalog["documents"].get(f"{unit['document_id']}:{unit['source_version']}")
        if item is None or document is None or item["review_status"] != "approved" or document["access_scope"] != access_scope:
            continue
        semantic_score = _cosine(query_vector, unit["embedding"])
        lexical_score = len(query_tokens & tokens(unit["search_text"])) / max(len(query_tokens), 1)
        # Semantic similarity dominates; lexical signal only disambiguates terms.
        score = semantic_score * 0.85 + lexical_score * 0.15
        key = (unit["item_id"], unit["item_version"])
        record = {key: value for key, value in unit.items() if key not in {"embedding", "search_text"}}
        record.update({"score": score, "semantic_score": semantic_score, "keyword_score": lexical_score})
        if key not in by_item or score > by_item[key]["score"]:
            by_item[key] = record
    return sorted(by_item.values(), key=lambda hit: (-hit["score"], hit["item_id"], hit["item_version"]))[:limit]
