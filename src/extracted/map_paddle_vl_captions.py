#!/usr/bin/env python3
"""Map PaddleOCR image assets to nearby figure captions on the same page.

The mapper reads ``layout/page-XXXX.json`` and pairs an image with the nearest
caption using the original PDF coordinates.  It writes a reviewable JSON file;
it deliberately does not rewrite ``document.md`` because an incorrect caption
must not silently become published content.

Example:
    uv run python -m extracted.map_paddle_vl_captions \
        output/input-vl
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


IMAGE_LABELS = {"image", "chart", "header_image", "footer_image"}
CAPTION_LABELS = {"figure_title", "vision_footnote"}
CAPTION_PREFIX = re.compile(
    r"^(?:figure|fig\.?|illustration|image|chart|table|example|exhibit)\s*"
    r"(?:[A-Za-z]+\s*)?\d+(?:[-.:]\d+)*\b",
    flags=re.IGNORECASE,
)
HTML_TAG = re.compile(r"<[^>]+>")
IMAGE_REF = re.compile(r"\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
ASSET_NAME = re.compile(r"^page-(\d{4})-(\d+)\.[^.]+$")


def _raw_page(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("res")
    return nested if isinstance(nested, dict) else payload


def _bbox(block: dict[str, Any]) -> tuple[float, float, float, float] | None:
    # PP-StructureV3 exports source_bbox after coordinate canonicalization.
    # PaddleOCR-VL extractions currently expose block_bbox directly.
    value = block.get("source_bbox") or block.get("block_bbox")
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        left, top, right, bottom = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _plain_text(value: str) -> str:
    text = html.unescape(HTML_TAG.sub(" ", value))
    text = re.sub(r"^[#>*\-\s]+", "", text)
    return " ".join(text.split())


def _is_caption(block: dict[str, Any], text: str) -> bool:
    return block.get("block_label") in CAPTION_LABELS or bool(CAPTION_PREFIX.match(text))


def _assets_for_page(image_dir: Path, page_number: int) -> list[Path]:
    assets: list[tuple[int, Path]] = []
    for path in image_dir.glob(f"page-{page_number:04d}-*.*"):
        match = ASSET_NAME.match(path.name)
        if match and int(match.group(1)) == page_number:
            assets.append((int(match.group(2)), path))
    return [path for _, path in sorted(assets)]


def _structure_asset_for_block(
    image_dir: Path,
    label: str | None,
    bbox: tuple[float, float, float, float],
) -> Path | None:
    """Resolve PP-StructureV3's ``img_in_<label>_box_<bbox>`` asset name."""
    if not label:
        return None
    coordinates: list[str] = []
    for value in bbox:
        if not float(value).is_integer():
            return None
        coordinates.append(str(int(value)))
    stem = f"img_in_{label}_box_{'_'.join(coordinates)}"
    matches = sorted(path for path in image_dir.glob(f"{stem}.*") if path.is_file())
    return matches[0] if matches else None


def _image_directory(extraction_dir: Path) -> Path:
    """Support PaddleOCR-VL's images/ and PP-StructureV3's imgs/."""
    for name in ("images", "imgs"):
        candidate = extraction_dir / name
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        "Expected images/ (PaddleOCR-VL) or imgs/ (PP-StructureV3) "
        "in the extraction directory."
    )


def _axis_overlap(first_start: float, first_end: float, second_start: float, second_end: float) -> float:
    return max(0.0, min(first_end, second_end) - max(first_start, second_start))


def _pair_score(
    image_bbox: tuple[float, float, float, float],
    caption_bbox: tuple[float, float, float, float],
) -> tuple[float, str, float]:
    """Score one image/caption pair; higher values mean closer/better aligned."""
    ix1, iy1, ix2, iy2 = image_bbox
    cx1, cy1, cx2, cy2 = caption_bbox
    image_width, image_height = ix2 - ix1, iy2 - iy1
    caption_width, caption_height = cx2 - cx1, cy2 - cy1
    horizontal_overlap = _axis_overlap(ix1, ix2, cx1, cx2)
    vertical_overlap = _axis_overlap(iy1, iy2, cy1, cy2)
    horizontal_gap = max(ix1 - cx2, cx1 - ix2, 0.0)
    vertical_gap = max(iy1 - cy2, cy1 - iy2, 0.0)
    gap = math.hypot(horizontal_gap, vertical_gap)

    if vertical_overlap > 0 and horizontal_gap > 0:
        relation = "left" if cx2 <= ix1 else "right"
        alignment = vertical_overlap / min(image_height, caption_height)
    elif horizontal_overlap > 0 and vertical_gap > 0:
        relation = "above" if cy2 <= iy1 else "below"
        alignment = horizontal_overlap / min(image_width, caption_width)
    elif horizontal_overlap > 0 and vertical_overlap > 0:
        relation = "overlapping"
        alignment = max(
            horizontal_overlap / min(image_width, caption_width),
            vertical_overlap / min(image_height, caption_height),
        )
    else:
        relation = "diagonal"
        alignment = 0.0

    # Captions normally sit beside, above, or below the corresponding image.
    # A 250-pixel gap is deliberately conservative for the PDF raster scale;
    # farther pairs remain in the review report as unmatched.
    if gap > 250:
        return 0.0, relation, gap
    score = 100.0 * (0.35 + 0.65 * min(alignment, 1.0)) / (1.0 + gap / 90.0)
    return round(score, 2), relation, round(gap, 2)


def _confidence(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _map_page(page_number: int, layout_path: Path, image_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    payload = json.loads(layout_path.read_text(encoding="utf-8"))
    blocks = _raw_page(payload).get("parsing_res_list", [])
    if not isinstance(blocks, list):
        return [], [], 0

    images: list[dict[str, Any]] = []
    captions: list[dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        bbox = _bbox(block)
        content = str(block.get("block_content") or "")
        if bbox is None:
            continue
        if block.get("block_label") in IMAGE_LABELS:
            source_match = IMAGE_REF.search(content)
            images.append(
                {
                    "bbox": bbox,
                    "label": block.get("block_label"),
                    "source_asset": source_match.group(1) if source_match else None,
                }
            )
        else:
            text = _plain_text(content)
            if text and _is_caption(block, text):
                captions.append(
                    {
                        "bbox": bbox,
                        "label": block.get("block_label"),
                        "text": text,
                    }
                )

    # PaddleOCR-VL numbers assets per page. PP-StructureV3 instead encodes the
    # layout label and bbox in each filename, so it can be resolved exactly.
    images.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
    if image_dir.name == "imgs":
        for image in images:
            asset = _structure_asset_for_block(image_dir, image.get("label"), image["bbox"])
            image["asset"] = str(asset.relative_to(image_dir.parent)) if asset else None
            image["asset_mapping_status"] = "matched_by_bbox_filename" if asset else "missing_asset"
    else:
        assets = _assets_for_page(image_dir, page_number)
        for index, image in enumerate(images):
            image["asset"] = str(assets[index].relative_to(image_dir.parent)) if index < len(assets) else None
            image["asset_mapping_status"] = "matched_by_page_order" if index < len(assets) else "missing_asset"

    candidates: list[tuple[float, int, int, str, float]] = []
    for image_index, image in enumerate(images):
        for caption_index, caption in enumerate(captions):
            score, relation, gap = _pair_score(image["bbox"], caption["bbox"])
            if score:
                candidates.append((score, image_index, caption_index, relation, gap))

    # Greedy global assignment prevents a nearby caption from being attached
    # to two adjacent music examples.
    matched_images: set[int] = set()
    matched_captions: set[int] = set()
    matches: list[dict[str, Any]] = []
    for score, image_index, caption_index, relation, gap in sorted(candidates, reverse=True):
        if image_index in matched_images or caption_index in matched_captions:
            continue
        image, caption = images[image_index], captions[caption_index]
        matched_images.add(image_index)
        matched_captions.add(caption_index)
        matches.append(
            {
                "page": page_number,
                "asset": image["asset"],
                "asset_mapping_status": image["asset_mapping_status"],
                "source_asset": image["source_asset"],
                "image_label": image["label"],
                "image_bbox": image["bbox"],
                "caption": caption["text"],
                "caption_label": caption["label"],
                "caption_bbox": caption["bbox"],
                "relation": relation,
                "gap_pixels": gap,
                "score": score,
                "confidence": _confidence(score),
                "needs_review": True,
            }
        )

    unmatched: list[dict[str, Any]] = []
    for index, image in enumerate(images):
        if index not in matched_images:
            unmatched.append({"kind": "image", "page": page_number, "asset": image["asset"], "bbox": image["bbox"]})
    for index, caption in enumerate(captions):
        if index not in matched_captions:
            unmatched.append({"kind": "caption", "page": page_number, "caption": caption["text"], "bbox": caption["bbox"]})
    return matches, unmatched, len(captions)


def build_map(extraction_dir: Path, destination: Path | None = None) -> Path:
    """Build a reviewable asset-to-caption map for an existing VL extraction."""
    layout_dir = extraction_dir / "layout"
    if not layout_dir.is_dir():
        raise FileNotFoundError("Expected layout/ in the extraction directory.")
    image_dir = _image_directory(extraction_dir)
    destination = destination or extraction_dir / "image-caption-map.json"

    all_matches: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    captions_detected = 0
    for layout_path in sorted(layout_dir.glob("page-*.json")):
        match = re.fullmatch(r"page-(\d{4})\.json", layout_path.name)
        if not match:
            continue
        page_matches, page_unmatched, count = _map_page(int(match.group(1)), layout_path, image_dir)
        all_matches.extend(page_matches)
        unmatched.extend(page_unmatched)
        captions_detected += count

    report = {
        "engine": "PaddleOCR layout caption mapper",
        "asset_directory": image_dir.name,
        "extraction_dir": str(extraction_dir),
        "matching_method": "same-page bounding-box proximity with one-to-one assignment",
        "review_required": True,
        "captions_detected": captions_detected,
        "images_matched": len(all_matches),
        "matches": sorted(all_matches, key=lambda item: (item["page"], item["asset"] or "")),
        "unmatched": unmatched,
    }
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extraction_dir", type=Path, help="Directory produced by paddle_vl_pdf_to_md")
    parser.add_argument("-o", "--output", type=Path, help="JSON report path (default: <extraction-dir>/image-caption-map.json)")
    args = parser.parse_args()
    try:
        output = build_map(args.extraction_dir, args.output)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"Wrote reviewable image/caption map: {output}")


if __name__ == "__main__":
    main()
