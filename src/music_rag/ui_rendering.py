"""Reusable pure helpers for the legacy Gradio compatibility surface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .util import require_within


def display_status(code: str) -> str:
    """Map a stable status code to fixed UI text without model output."""
    messages = {
        "ready": "Ready.",
        "no_match": "No approved document matched this request.",
        "semantic_unavailable": "Semantic retrieval is unavailable.",
        "no_match_best_effort": "No complete match was found; showing the best final candidate.",
        "asset_invalid": "A source asset is invalid and cannot be displayed.",
        "system_error": "The document could not be loaded. Try again later.",
    }
    return messages.get(code, messages["system_error"])


def _safe_image_path(record: dict[str, Any], image: dict[str, Any]) -> Path | None:
    image_path = image.get("image_path")
    extraction_dir = record.get("extraction_dir")
    if not isinstance(image_path, str) or not isinstance(extraction_dir, str):
        return None
    try:
        path = require_within(Path(extraction_dir), Path(image_path))
    except ValueError:
        return None
    return path if path.is_file() else None


def chroma_asset_paths(chroma_dir: str | Path) -> list[str]:
    """Return existing sidecar-approved image paths for the UI allow-list."""
    sidecar = Path(chroma_dir) / "chunk-records.json"
    if not sidecar.is_file():
        return []
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    paths: set[str] = set()
    for record in payload.values():
        if not isinstance(record, dict):
            continue
        for image in record.get("images", []):
            if isinstance(image, dict):
                path = _safe_image_path(record, image)
                if path is not None:
                    paths.add(str(path))
    return sorted(paths)


__all__ = ["chroma_asset_paths", "display_status"]
