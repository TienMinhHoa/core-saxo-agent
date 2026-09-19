"""Operator-controlled chapter manifests for the Music Theory demo source."""
from __future__ import annotations

import re
from typing import Any

from .importer import ImportReport, import_markdown
from .store import CatalogStore

CHAPTER = re.compile(r"^Chapter\s+(\d+)\b", re.I)


def chapter_manifest(store: CatalogStore, report: ImportReport, *, approved: bool = False) -> dict[str, Any]:
    """Derive candidate chapter boundaries from explicit source headings.

    This creates a review manifest, not inferred exercises.  `approved=True`
    is intentionally reserved for an operator command with an explicit flag.
    """
    catalog = store.load()
    blocks = sorted(
        (block for block in catalog["blocks"].values() if block["document_id"] == report.document_id and block["source_version"] == report.source_version),
        key=lambda block: block["source_order"],
    )
    starts = [(index, block, CHAPTER.match(block["raw_text"])) for index, block in enumerate(blocks) if block["kind"] == "heading" and CHAPTER.match(block["raw_text"])]
    sections_by_heading = {section["heading_block_id"]: section for section in catalog["sections"].values()}
    items: list[dict[str, Any]] = []
    for position, (start, heading, match) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(blocks)
        section = sections_by_heading.get(heading["block_id"])
        if section is None:
            continue
        number = int(match.group(1))
        items.append({
            "item_id": f"chapter_{number:02d}", "item_version": 1, "section_id": section["section_id"],
            "item_type": "guideline", "content_block_ids": [block["block_id"] for block in blocks[start:end]],
            "required_context_refs": [], "verified_fields": {},
            "review_status": "approved" if approved else "needs_review",
        })
    return {"document_id": report.document_id, "source_version": report.source_version, "items": items}


def import_chapter_demo(store: CatalogStore, markdown: str, asset_root: str, *, approved: bool = False) -> tuple[ImportReport, dict[str, Any]]:
    report = import_markdown(
        store, markdown, asset_root=asset_root,
        title="Music Theory For Dummies", author="Michael Pilhofer and Holly Day", access_scope="public",
    )
    return report, chapter_manifest(store, report, approved=approved)
