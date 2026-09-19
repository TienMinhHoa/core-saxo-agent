"""Canonical geometry contract for OCR layout exported from a PDF.

The PDF viewer renders the original page raster.  Consequently, an OCR box is
safe to overlay only when it was detected on that same, unmodified raster.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


RAW_PDF_RASTER_SPACE = "raw_pdf_raster_pixels"
_TRANSFORMING_PREPROCESSORS = (
    "use_doc_orientation_classify",
    "use_doc_unwarping",
)


def _valid_dimension(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _source_bbox(value: Any) -> list[float | int] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    if any(not isinstance(item, (int, float)) or isinstance(item, bool) for item in value):
        return None
    left, top, right, bottom = value
    if right <= left or bottom <= top:
        return None
    return value.copy()


def canonicalize_raw_pdf_layout(payload: dict[str, Any]) -> dict[str, Any]:
    """Add source-space boxes after proving no page transform was applied.

    PP-StructureV3 reports its layout boxes in the image presented to the
    pipeline.  Rotation or document unwarping changes that image and Paddle's
    JSON does not retain an inverse transform.  Refuse to label such boxes as
    source boxes rather than emitting geometry that a PDF viewer cannot place
    correctly.
    """
    page = deepcopy(payload)
    preprocessor = page.get("doc_preprocessor_res")
    settings = preprocessor.get("model_settings") if isinstance(preprocessor, dict) else None
    if not isinstance(settings, dict):
        raise ValueError("Thiếu doc_preprocessor_res.model_settings; không thể xác nhận hệ tọa độ bbox.")
    enabled = [name for name in _TRANSFORMING_PREPROCESSORS if settings.get(name) is not False]
    if enabled:
        raise ValueError(
            "BBox không thuộc hệ tọa độ PDF gốc vì OCR preprocessing đang bật: "
            + ", ".join(enabled)
        )
    if not _valid_dimension(page.get("width")) or not _valid_dimension(page.get("height")):
        raise ValueError("Thiếu width/height hợp lệ cho hệ tọa độ PDF gốc.")

    blocks = page.get("parsing_res_list")
    if not isinstance(blocks, list):
        raise ValueError("Thiếu parsing_res_list trong kết quả OCR.")
    for block in blocks:
        if not isinstance(block, dict):
            continue
        bbox = _source_bbox(block.get("block_bbox"))
        if bbox is not None:
            block["source_bbox"] = bbox

    page["coordinate_space"] = {
        "name": RAW_PDF_RASTER_SPACE,
        "origin": "top_left",
        "x_axis": "right",
        "y_axis": "down",
        "width": page["width"],
        "height": page["height"],
        "transform_to_source": "identity",
    }
    return page
