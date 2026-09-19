"""Agentic retrieval service backed by the reviewed Chroma chunk index.

The service deliberately implements the small interface consumed by
``AgenticRetriever``.  This keeps the query → candidate inspection → optional
rewrite/retry → source-only response contract while replacing the legacy
catalog semantic index with Chroma vectors and its image sidecar.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .chroma_chunks import search_chroma_chunks
from .embeddings import EmbeddingProvider
from .errors import AccessDenied, NotFound, ValidationError
from .util import require_within, stable_id


class ChromaChunkService:
    """Expose Chroma chunks using the interface expected by AgenticRetriever."""

    def __init__(
        self,
        persist_dir: str | Path,
        collection_name: str,
        *,
        source_scope: str = "public",
        limit: int = 10,
    ) -> None:
        if limit < 1:
            raise ValueError("chroma_limit_must_be_positive")
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name
        self.source_scope = source_scope
        self.limit = limit
        self._candidate_sets: dict[str, dict[str, Any]] = {}

    def understand_request(self, request: str) -> dict[str, Any]:
        return {"query": request.strip(), "hard_constraints": [], "optional_constraints": []}

    def search_semantic(
        self,
        query: str,
        access_scope: str,
        provider: EmbeddingProvider,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if access_scope != self.source_scope:
            return []
        return search_chroma_chunks(
            query,
            persist_dir=self.persist_dir,
            collection_name=self.collection_name,
            provider=provider,
            limit=min(limit, self.limit),
        )

    @staticmethod
    def _asset_block(chunk_id: str, index: int, image: dict[str, Any]) -> dict[str, Any]:
        figure_number = image.get("figure_number") or "figure"
        figure_title = image.get("figure_title") or ""
        caption = image.get("caption") or image.get("summary") or ""
        label = " ".join(str(part) for part in (figure_number, figure_title, caption) if part).strip()
        return {
            "block_id": f"{chunk_id}:asset:{index}",
            "kind": "asset",
            "raw_text": label,
            "asset_ref": image.get("asset_ref"),
        }

    def get_material_candidates(
        self,
        hits: list[dict[str, Any]],
        access_scope: str,
        inspect_limit: int = 3,
    ) -> dict[str, Any]:
        if access_scope != self.source_scope:
            candidates: list[dict[str, Any]] = []
        else:
            candidates = []
            for hit in hits[:inspect_limit]:
                chunk_id = str(hit.get("chunk_id") or "").strip()
                if not chunk_id:
                    continue
                header = str(hit.get("header") or "")
                content = str(hit.get("content") or "")
                blocks: list[dict[str, Any]] = []
                if header:
                    blocks.append({
                        "block_id": f"{chunk_id}:header",
                        "kind": "heading",
                        "raw_text": header,
                        "asset_ref": None,
                    })
                blocks.append({
                    "block_id": f"{chunk_id}:text",
                    "kind": "text",
                    "raw_text": content,
                    "asset_ref": None,
                })
                for image_index, image in enumerate(hit.get("images", [])):
                    if isinstance(image, dict):
                        blocks.append(self._asset_block(chunk_id, image_index, image))
                candidates.append({
                    "item_id": chunk_id,
                    "item_version": 1,
                    "evidence_block_ids": [block["block_id"] for block in blocks],
                    "item": {"item_id": chunk_id, "item_version": 1, "review_status": "approved"},
                    "blocks": blocks,
                    "record": hit,
                })
        candidate_set_id = stable_id(
            "chroma_candidate_set",
            str(time.time_ns()),
            *(f"{candidate['item_id']}:1" for candidate in candidates),
        )
        candidate_set = {
            "candidate_set_id": candidate_set_id,
            "access_scope": access_scope,
            "candidates": candidates,
        }
        self._candidate_sets[candidate_set_id] = candidate_set
        return candidate_set

    def validate_selection(self, decision: dict[str, Any], access_scope: str) -> dict[str, Any]:
        candidate_set = self._candidate_sets.get(decision.get("candidate_set_id"))
        if candidate_set is None:
            raise NotFound("candidate_set_expired")
        if candidate_set["access_scope"] != access_scope or access_scope != self.source_scope:
            raise AccessDenied("candidate_set_scope_mismatch")
        if decision.get("status") != "selected":
            return decision
        valid_ids = {
            (candidate["item_id"], candidate["item_version"])
            for candidate in candidate_set["candidates"]
        }
        selected = decision.get("selected_items")
        if not isinstance(selected, list) or not selected:
            raise ValidationError("selected_items_missing")
        for item in selected:
            if not isinstance(item, dict) or (item.get("item_id"), item.get("item_version")) not in valid_ids:
                raise ValidationError("selected_chunk_not_in_candidate_set")
        return decision

    def build_source_response(self, decision: dict[str, Any], access_scope: str) -> dict[str, Any]:
        decision = self.validate_selection(decision, access_scope)
        if decision.get("status") != "selected":
            return {"status": decision.get("status"), "reason_code": decision.get("reason_code")}
        candidate_set = self._candidate_sets[decision["candidate_set_id"]]
        selected_keys = {
            (item["item_id"], item["item_version"])
            for item in decision["selected_items"]
        }
        items: list[dict[str, Any]] = []
        for candidate in candidate_set["candidates"]:
            if (candidate["item_id"], candidate["item_version"]) not in selected_keys:
                continue
            record = candidate["record"]
            items.append({
                "item_id": candidate["item_id"],
                "item_version": candidate["item_version"],
                "item_type": "header_chunk",
                "source": {"title": "Music Theory For Dummies", "author": "Paddle/VLM extraction"},
                "blocks": candidate["blocks"],
                "record": record,
            })
        if not items:
            raise ValidationError("selected_chunk_not_available")
        return {
            "status": "selected",
            "candidate_set_id": decision["candidate_set_id"],
            "items": items,
            "ui": {"renderer": "chroma_source_blocks_only", "generated_answer": False},
        }

    def asset_path(self, item_id: str, item_version: int, block_id: str, access_scope: str) -> Path:
        """Validate and resolve a Chroma sidecar image for callers needing a path gate."""
        if access_scope != self.source_scope or item_version != 1:
            raise AccessDenied("asset_scope_invalid")
        prefix = f"{item_id}:asset:"
        if not block_id.startswith(prefix):
            raise NotFound("asset_not_in_chroma_chunk")
        try:
            image_index = int(block_id[len(prefix):])
        except ValueError as exc:
            raise NotFound("asset_not_in_chroma_chunk") from exc
        sidecar = self.persist_dir / "chunk-records.json"
        try:
            records = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise NotFound("chroma_sidecar_missing") from exc
        record = records.get(item_id) if isinstance(records, dict) else None
        images = record.get("images", []) if isinstance(record, dict) else []
        if not isinstance(images, list) or image_index < 0 or image_index >= len(images):
            raise NotFound("asset_not_in_chroma_chunk")
        image = images[image_index]
        if not isinstance(record, dict) or not isinstance(image, dict):
            raise NotFound("asset_not_in_chroma_chunk")
        image_path = image.get("image_path")
        extraction_dir = record.get("extraction_dir")
        if not isinstance(image_path, str) or not isinstance(extraction_dir, str):
            raise NotFound("asset_invalid")
        try:
            path = require_within(Path(extraction_dir), Path(image_path))
        except ValueError as exc:
            raise ValidationError("asset_path_outside_root") from exc
        if not path.is_file():
            raise NotFound("asset_missing")
        return path
