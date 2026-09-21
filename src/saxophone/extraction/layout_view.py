"""Read validated extraction layout data for presentation adapters."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .layout import finite_number, is_raw_pdf_raster_space, normalize_blocks


def read_layout_pages(
    layout_dir: Path,
    page_url: Callable[[int], str],
) -> list[dict[str, Any]]:
    """Return browser-ready pages while ignoring invalid persisted payloads."""
    pages: list[dict[str, Any]] = []
    for path in sorted(layout_dir.glob("page-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            width, height = finite_number(payload.get("width")), finite_number(
                payload.get("height")
            )
            if width is None or height is None or width <= 0 or height <= 0:
                continue
            if not is_raw_pdf_raster_space(payload.get("coordinate_space")):
                continue
            page_index = payload.get("page_index")
            page = int(page_index) + 1 if isinstance(page_index, int) else len(pages) + 1
            pages.append(
                {
                    "page": page,
                    "width": width,
                    "height": height,
                    "image_url": page_url(page),
                    "blocks": normalize_blocks(payload),
                }
            )
        except (OSError, ValueError, TypeError):
            continue
    return pages
