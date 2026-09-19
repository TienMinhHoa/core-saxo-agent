"""Approved-only item retrieval. Search units are never renderable content."""
from __future__ import annotations

from typing import Any

from .store import CatalogStore
from .util import normalise_for_search, tokens

ALIASES = {
    "gam trưởng": "major scales",
    "gam truong": "major scales",
    "đa điệu": "polytonal",
    "da dieu": "polytonal",
    "hướng dẫn tác giả": "author notes",
    "huong dan tac gia": "author notes",
}


def query_for_search(query: str) -> str:
    normalised = normalise_for_search(query)
    # Aliases may be a phrase within a longer request.  They expand the index
    # query only; the source text passed to the renderer is never translated.
    expansions = [english for vietnamese, english in ALIASES.items() if vietnamese in normalised]
    return f"{normalised} {' '.join(expansions)}".strip()


def build_index(store: CatalogStore) -> dict[str, int]:
    catalog = store.load()
    catalog["search_units"] = {}
    indexed = 0
    skipped = 0
    for key, item in catalog["items"].items():
        if item["review_status"] != "approved":
            skipped += 1
            continue
        from pathlib import Path
        from .util import sha256_file
        asset_invalid = any(
            catalog["blocks"].get(block_id, {}).get("kind") == "asset"
            and (
                not catalog["blocks"].get(block_id, {}).get("asset_path")
                or not Path(catalog["blocks"][block_id]["asset_path"]).is_file()
                or sha256_file(Path(catalog["blocks"][block_id]["asset_path"]))
                != catalog["blocks"][block_id].get("asset_hash")
            )
            for block_id in item["content_block_ids"]
        )
        if asset_invalid:
            skipped += 1
            continue
        unit_id = f"search_{key}"
        catalog["search_units"][unit_id] = {
            "search_unit_id": unit_id,
            "item_id": item["item_id"],
            "item_version": item["item_version"],
            "search_text": item["search_text"],
            "evidence_block_ids": list(item["content_block_ids"]),
            "evidence_scope": "item",
            "document_id": item["document_id"],
            "source_version": item["source_version"],
        }
        indexed += 1
    store.save(catalog)
    return {"indexed": indexed, "skipped": skipped}


def search_materials(store: CatalogStore, query: str, access_scope: str, limit: int = 10) -> list[dict[str, Any]]:
    query_tokens = tokens(query_for_search(query))
    catalog = store.load()
    ranked: list[tuple[int, dict[str, Any]]] = []
    for unit in catalog["search_units"].values():
        item = catalog["items"].get(f"{unit['item_id']}:{unit['item_version']}")
        document = catalog["documents"].get(f"{unit['document_id']}:{unit['source_version']}")
        if item is None or document is None or document["access_scope"] != access_scope or item["review_status"] != "approved":
            continue
        score = len(query_tokens & tokens(unit["search_text"]))
        if score:
            ranked.append((score, unit))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["item_id"], pair[1]["item_version"]))
    return [{"score": score, **unit} for score, unit in ranked[:limit]]
