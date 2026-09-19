"""Draft-only Markdown/Paddle import with source provenance preserved."""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .store import CatalogStore
from .util import normalise_for_search, require_within, sha256_file, stable_id

RAW_PDF_RASTER_SPACE = "raw_pdf_raster_pixels"

MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)")
HTML_IMAGE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*([\"'])(.*?)\1[^>]*>", re.I)
MARKDOWN_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
DIV_TEXT = re.compile(r"^\s*<div\b[^>]*>(.*?)</div>\s*$", re.I)
TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class ImportReport:
    document_id: str
    source_version: str
    imported: bool
    block_count: int
    asset_references: int
    missing_assets: list[str]
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_version": self.source_version,
            "imported": self.imported,
            "block_count": self.block_count,
            "asset_references": self.asset_references,
            "missing_assets": self.missing_assets,
            "warnings": self.warnings,
            "review_status": "draft",
            "indexed": False,
        }


def _title_from_markdown(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        match = MARKDOWN_HEADING.match(line)
        if match:
            return match.group(2).strip()
    return fallback


def _asset_reference(line: str) -> str | None:
    match = HTML_IMAGE.search(line) or MARKDOWN_IMAGE.search(line)
    return html.unescape(match.group(2) if match and match.re is HTML_IMAGE else match.group(1)) if match else None


def _heading(line: str) -> tuple[int, str] | None:
    match = MARKDOWN_HEADING.match(line)
    if match:
        return len(match.group(1)), match.group(2).strip()
    match = DIV_TEXT.match(line)
    if not match or "<img" in line.casefold():
        return None
    value = html.unescape(TAG.sub("", match.group(1))).strip()
    # Layout Markdown frequently keeps section headings inside a centre div.
    if value and len(value) <= 180 and not value.endswith("."):
        return 2, value
    return None


def _safe_asset(asset_root: Path, reference: str) -> tuple[str | None, str | None]:
    """Return resolved asset and checksum; URLs and unsafe paths stay missing."""
    if "://" in reference or reference.startswith(("/", "\\")):
        return None, None
    try:
        candidate = require_within(asset_root, asset_root / reference)
    except ValueError:
        return None, None
    if not candidate.is_file():
        return None, None
    return str(candidate), sha256_file(candidate)


def _layout_locators(layout_dir: Path | None) -> dict[str, dict[str, Any]]:
    """Return only unambiguous text-to-layout mappings from Paddle JSON.

    A filename, OCR order, or a bounding-box number is never used to infer a
    page.  Exact duplicate OCR text therefore intentionally remains unmapped.
    """
    if layout_dir is None:
        return {}
    candidates: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(layout_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            page_index = payload["page_index"]
            width, height = payload.get("width"), payload.get("height")
            blocks = payload.get("parsing_res_list", [])
            coordinate_space = payload.get("coordinate_space")
        except (OSError, ValueError, TypeError, KeyError):
            continue
        if (
            not isinstance(page_index, int)
            or not isinstance(blocks, list)
            or not isinstance(coordinate_space, dict)
            or coordinate_space.get("name") != RAW_PDF_RASTER_SPACE
            or coordinate_space.get("transform_to_source") != "identity"
        ):
            continue
        for block in blocks:
            if not isinstance(block, dict) or not isinstance(block.get("block_content"), str):
                continue
            value = block["block_content"].strip()
            if not value:
                continue
            # Locator boxes must use the source coordinate contract.  Legacy
            # block_bbox may refer to a rotated or unwarped OCR image.
            source_bbox = block.get("source_bbox")
            if not isinstance(source_bbox, list) or len(source_bbox) != 4:
                continue
            candidates.setdefault(value, []).append({
                "page_index": page_index,
                "printed_page": None,
                "bbox": source_bbox,
                "coordinate_space": {
                    "name": "raw_pdf_raster_pixels",
                    "width": width,
                    "height": height,
                    "transform": "identity",
                },
                "paddle_block_id": block.get("block_id"),
                "paddle_block_label": block.get("block_label"),
                "paddle_block_order": block.get("block_order"),
            })
    return {text: locators[0] for text, locators in candidates.items() if len(locators) == 1}


def import_markdown(
    store: CatalogStore,
    markdown_path: str | Path,
    *,
    asset_root: str | Path,
    title: str | None = None,
    author: str | None = None,
    access_scope: str = "private",
    layout_json_dir: str | Path | None = None,
) -> ImportReport:
    """Import source blocks as *draft*; this function never creates an item."""
    source = Path(markdown_path)
    assets = Path(asset_root)
    raw = source.read_bytes()
    markdown = raw.decode("utf-8")
    source_hash = sha256_file(source)
    source_version = source_hash
    document_title = title or _title_from_markdown(markdown, source.stem)
    document_id = stable_id("doc", str(source.resolve()), document_title)
    catalog = store.load()
    layout_dir = Path(layout_json_dir) if layout_json_dir is not None else None
    locator_by_text = _layout_locators(layout_dir)
    document_key = f"{document_id}:{source_version}"
    if document_key in catalog["documents"]:
        blocks = [b for b in catalog["blocks"].values() if b["document_id"] == document_id and b["source_version"] == source_version]
        missing = [b["asset_ref"] for b in blocks if b["kind"] == "asset" and not b.get("asset_path")]
        return ImportReport(document_id, source_version, False, len(blocks), len(missing) + sum(1 for b in blocks if b["kind"] == "asset" and b.get("asset_path")), missing, ["idempotent_reimport"])

    catalog["documents"][document_key] = {
        "document_id": document_id,
        "source_version": source_version,
        "source_hash": source_hash,
        "title": document_title,
        "author": author,
        "access_scope": access_scope,
        "source_path": str(source.resolve()),
        "asset_root": str(assets.resolve()),
        "layout_json_dir": str(layout_dir.resolve()) if layout_dir is not None else None,
        "review_status": "draft",
    }
    sections: list[tuple[str, int, int]] = []
    missing_assets: list[str] = []
    asset_count = 0
    block_count = 0
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        if not line.strip():
            continue
        asset_ref = _asset_reference(line)
        heading = _heading(line)
        if asset_ref is not None:
            kind = "asset"
            asset_count += 1
            raw_text = ""
            asset_path, asset_hash = _safe_asset(assets, asset_ref)
            if asset_path is None:
                missing_assets.append(asset_ref)
        elif heading:
            kind = "heading"
            raw_text = heading[1]
            asset_path = asset_hash = None
        else:
            kind = "text"
            raw_text = line
            asset_path = asset_hash = None
        block_count += 1
        block_id = stable_id("block", document_id, source_version, str(line_number), line)
        locator = {"md_line": line_number, "page_index": None, "printed_page": None}
        if kind != "asset" and raw_text in locator_by_text:
            locator.update(locator_by_text[raw_text])
        block = {
            "block_id": block_id,
            "document_id": document_id,
            "source_version": source_version,
            "kind": kind,
            "raw_text": raw_text,
            "asset_ref": asset_ref,
            "asset_path": asset_path,
            "asset_hash": asset_hash,
            "locator": locator,
            "source_order": block_count,
        }
        catalog["blocks"][block_id] = block
        if heading:
            level, heading_text = heading
            while sections and sections[-1][1] >= level:
                sections.pop()
            parent = sections[-1][0] if sections else None
            section_id = stable_id("section", document_id, source_version, block_id)
            catalog["sections"][section_id] = {
                "section_id": section_id,
                "document_id": document_id,
                "source_version": source_version,
                "parent_section_id": parent,
                "heading_block_id": block_id,
                "title_raw": heading_text,
                "title_for_search": normalise_for_search(heading_text),
                "source_order": block_count,
                "review_status": "needs_review",
            }
            sections.append((section_id, level, block_count))
    store.save(catalog)
    warnings = ["markdown_only_provenance: page_index_and_printed_page_are_null"]
    if missing_assets:
        warnings.append("missing_assets: draft_is_not_publishable")
    return ImportReport(document_id, source_version, True, block_count, asset_count, missing_assets, warnings)
