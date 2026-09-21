"""Pure normalization of extracted PDF layout payloads."""

from __future__ import annotations

import math
from typing import Any

RAW_PDF_RASTER_SPACE = "raw_pdf_raster_pixels"


def is_raw_pdf_raster_space(value: Any) -> bool:
    """Return whether metadata declares the supported source coordinate space."""
    return (
        isinstance(value, dict)
        and value.get("name") == RAW_PDF_RASTER_SPACE
        and value.get("transform_to_source") == "identity"
    )


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def normalize_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose stable viewer fields and only validated source-space boxes."""

    blocks: list[dict[str, Any]] = []
    raw_blocks = payload.get("parsing_res_list", [])
    if not isinstance(raw_blocks, list):
        return blocks
    for index, raw in enumerate(raw_blocks):
        if not isinstance(raw, dict):
            continue
        bbox = raw.get("source_bbox")
        clean_bbox: list[float] | None = None
        if isinstance(bbox, list) and len(bbox) == 4:
            coordinates = [finite_number(item) for item in bbox]
            if all(item is not None for item in coordinates):
                left, top, right, bottom = coordinates
                if right > left and bottom > top:
                    clean_bbox = [left, top, right, bottom]
        text = raw.get("block_content")
        blocks.append(
            {
                "id": raw.get("block_id", index),
                "order": raw.get("block_order", index + 1),
                "label": str(raw.get("block_label", "unknown")),
                "text": text if isinstance(text, str) else "",
                "bbox": clean_bbox,
            }
        )
    return blocks
