"""Runtime orchestration that returns source blocks, never generated answers."""
from __future__ import annotations

import html
import time
from pathlib import Path
from typing import Any

from .contracts import validate_decision
from .embeddings import EmbeddingProvider
from .errors import AccessDenied, AssetError, NotFound, ValidationError
from .search import search_materials
from .semantic import semantic_search
from .store import CatalogStore
from .util import ordered_unique, require_within, stable_id


class MusicMaterialService:
    def __init__(self, store: CatalogStore) -> None:
        self.store = store
        self._candidate_sets: dict[str, dict[str, Any]] = {}
        self._verified_assets: dict[str, tuple[int, int]] = {}

    def understand_request(self, request: str) -> dict[str, Any]:
        """A deliberately conservative normaliser, not an answer-writing step."""
        return {"query": request.strip(), "hard_constraints": [], "optional_constraints": []}

    def search_materials(self, query: str, access_scope: str, limit: int = 10) -> list[dict[str, Any]]:
        return search_materials(self.store, query, access_scope, limit=limit)

    def search_semantic(self, query: str, access_scope: str, provider: EmbeddingProvider, limit: int = 10) -> list[dict[str, Any]]:
        return semantic_search(self.store, provider, query, access_scope, limit=limit)

    def get_material_candidates(self, hits: list[dict[str, Any]], access_scope: str, inspect_limit: int = 3) -> dict[str, Any]:
        catalog = self.store.load()
        candidates: list[dict[str, Any]] = []
        for hit in hits[:inspect_limit]:
            key = f"{hit['item_id']}:{hit['item_version']}"
            item = catalog["items"].get(key)
            document = catalog["documents"].get(f"{hit['document_id']}:{hit['source_version']}")
            if item is None or document is None or document["access_scope"] != access_scope or item["review_status"] != "approved":
                continue
            blocks = [catalog["blocks"][block_id] for block_id in item["content_block_ids"]]
            candidates.append({
                "item_id": item["item_id"], "item_version": item["item_version"],
                "evidence_block_ids": list(item["content_block_ids"]), "item": item, "blocks": blocks,
            })
        candidate_set_id = stable_id("candidate_set", str(time.time_ns()), *(f"{x['item_id']}:{x['item_version']}" for x in candidates))
        candidate_set = {"candidate_set_id": candidate_set_id, "access_scope": access_scope, "candidates": candidates}
        self._candidate_sets[candidate_set_id] = candidate_set
        return candidate_set

    def validate_selection(self, decision: dict[str, Any], access_scope: str) -> dict[str, Any]:
        candidate_set = self._candidate_sets.get(decision.get("candidate_set_id"))
        if candidate_set is None:
            raise NotFound("candidate_set_expired")
        if candidate_set["access_scope"] != access_scope:
            raise AccessDenied("candidate_set_scope_mismatch")
        decision = validate_decision(decision, candidate_set)
        if decision["status"] != "selected":
            return decision
        # Re-read state to prevent a stale candidate set from changing version/status.
        catalog = self.store.load()
        for chosen in decision["selected_items"]:
            item = catalog["items"].get(f"{chosen['item_id']}:{chosen['item_version']}")
            if item is None or item["review_status"] != "approved":
                raise ValidationError("selected_item_no_longer_approved")
            document = catalog["documents"].get(f"{item['document_id']}:{item['source_version']}")
            if document is None or document["access_scope"] != access_scope:
                raise AccessDenied("selected_item_scope_invalid")
        return decision

    def select_top_candidate(self, candidate_set: dict[str, Any]) -> dict[str, Any]:
        """Deterministic selector used by the MVP agent; it returns IDs only."""
        if not candidate_set["candidates"]:
            return {"status": "no_match", "candidate_set_id": candidate_set["candidate_set_id"], "reason_code": "no_approved_match"}
        candidate = candidate_set["candidates"][0]
        return {
            "status": "selected", "candidate_set_id": candidate_set["candidate_set_id"],
            "selected_items": [{"item_id": candidate["item_id"], "item_version": candidate["item_version"]}],
            "evidence_block_ids": [candidate["evidence_block_ids"][0]],
        }

    def build_source_response(self, decision: dict[str, Any], access_scope: str) -> dict[str, Any]:
        decision = self.validate_selection(decision, access_scope)
        if decision["status"] != "selected":
            return {"status": decision["status"], "reason_code": decision["reason_code"]}
        catalog = self.store.load()
        selected_keys = [f"{item['item_id']}:{item['item_version']}" for item in decision["selected_items"]]
        expanded: list[str] = []
        def include(key: str) -> None:
            if key in expanded:
                return
            item = catalog["items"].get(key)
            if item is None or item["review_status"] != "approved":
                raise ValidationError("dependency_not_available")
            for ref in item["required_context_refs"]:
                include(f"{ref['item_id']}:{ref['item_version']}")
            expanded.append(key)
        for key in selected_keys:
            include(key)
        return {
            "status": "selected",
            "candidate_set_id": decision["candidate_set_id"],
            "items": [self._render_item(catalog, catalog["items"][key], access_scope) for key in expanded],
            "ui": {"renderer": "source_blocks_only", "generated_answer": False},
        }

    def _render_item(self, catalog: dict[str, Any], item: dict[str, Any], access_scope: str) -> dict[str, Any]:
        document = catalog["documents"].get(f"{item['document_id']}:{item['source_version']}")
        if document is None or document["access_scope"] != access_scope:
            raise AccessDenied("document_scope_invalid")
        blocks = []
        for block_id in item["content_block_ids"]:
            block = dict(catalog["blocks"][block_id])
            # Escaping is a display transformation only.  It prevents a source
            # document from supplying executable HTML to a chat/web renderer.
            rendered = {key: block[key] for key in ("block_id", "kind", "locator", "source_order")}
            if block["kind"] != "asset":
                rendered["text"] = html.escape(block["raw_text"], quote=False)
            if block["kind"] == "asset":
                rendered["asset"] = {"asset_ref": block["asset_ref"], "asset_hash": block["asset_hash"]}
            blocks.append(rendered)
        return {
            "item_id": item["item_id"], "item_version": item["item_version"], "item_type": item["item_type"],
            "document_id": item["document_id"], "source_version": item["source_version"],
            "source": {"title": document["title"], "author": document["author"]}, "blocks": blocks,
        }

    def asset_path(self, item_id: str, item_version: int, block_id: str, access_scope: str) -> Path:
        """Authorization/validation gate to be called by an HTTP asset endpoint."""
        catalog = self.store.load()
        item = catalog["items"].get(f"{item_id}:{item_version}")
        if item is None or item["review_status"] != "approved" or block_id not in item["content_block_ids"]:
            raise NotFound("asset_not_in_approved_item")
        document = catalog["documents"].get(f"{item['document_id']}:{item['source_version']}")
        if document is None or document["access_scope"] != access_scope:
            raise AccessDenied("asset_scope_invalid")
        block = catalog["blocks"][block_id]
        if block["kind"] != "asset" or not block.get("asset_path"):
            raise AssetError("asset_invalid")
        path = require_within(Path(document["asset_root"]), Path(block["asset_path"]))
        if not path.is_file():
            raise AssetError("asset_missing")
        from .util import sha256_file
        stat = path.stat()
        fingerprint = (stat.st_mtime_ns, stat.st_size)
        if self._verified_assets.get(block_id) != fingerprint and sha256_file(path) != block["asset_hash"]:
            raise AssetError("asset_checksum_invalid")
        self._verified_assets[block_id] = fingerprint
        return path
