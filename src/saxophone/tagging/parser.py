"""Deterministic paragraph parsing for normalized ingestion chunks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Mapping

from saxophone.ingestion.models import IngestionSourceChunk

from .models import ParagraphBlock

_PAGE_MARKER = re.compile(r"^##\s+Page\s+\d+\s*$", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_MARKDOWN_IMAGE = re.compile(r"!\[[^]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)")
_HTML_IMAGE = re.compile(r"<img\b[^>]*?\bsrc=[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)


@dataclass
class _Block:
    lines: list[str]
    heading_path: tuple[str, ...]
    image_refs: list[str]


def parse_chunk_paragraphs(
    chunk: IngestionSourceChunk,
    *,
    image_metadata: Mapping[str, Mapping[str, object]] | None = None,
) -> tuple[ParagraphBlock, ...]:
    """Split one chunk into stable paragraphs without rewriting source text."""
    metadata = image_metadata or {}
    blocks: list[_Block] = []
    current: _Block | None = None
    headings: list[str] = []
    pending_images: list[str] = []

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        text = "\n".join(current.lines)
        if text.strip():
            blocks.append(current)
        current = None

    for line in chunk.search_text.splitlines():
        if _PAGE_MARKER.match(line):
            flush()
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            headings[:] = headings[: level - 1]
            headings.append(heading.group(2).strip())
            continue
        image_refs = _extract_image_refs(line)
        if image_refs and _is_image_only(line):
            if blocks and current is None:
                blocks[-1].image_refs.extend(image_refs)
            else:
                pending_images.extend(image_refs)
            continue
        if not line.strip():
            flush()
            continue
        if current is None:
            current = _Block([], tuple(headings), [])
            if pending_images:
                current.image_refs.extend(pending_images)
                pending_images.clear()
        current.lines.append(line)
        if image_refs:
            current.image_refs.extend(image_refs)
    flush()

    if pending_images and blocks:
        blocks[-1].image_refs.extend(pending_images)
    return tuple(_to_paragraph(chunk.chunk_id, ordinal, block, metadata) for ordinal, block in enumerate(blocks))


def _to_paragraph(
    chunk_id: str,
    ordinal: int,
    block: _Block,
    image_metadata: Mapping[str, Mapping[str, object]],
) -> ParagraphBlock:
    refs = tuple(dict.fromkeys(block.image_refs))
    captions = {
        ref: str(image_metadata[ref]["caption"]).strip()
        for ref in refs
        if ref in image_metadata and isinstance(image_metadata[ref].get("caption"), str)
        and str(image_metadata[ref]["caption"]).strip()
    }
    digest = hashlib.sha256(f"{chunk_id}:{ordinal}".encode()).hexdigest()[:12]
    return ParagraphBlock(
        paragraph_id=f"{chunk_id}:p{ordinal:04d}-{digest}",
        chunk_id=chunk_id,
        ordinal=ordinal,
        text="\n".join(block.lines),
        heading_path=block.heading_path,
        image_refs=refs,
        image_captions=captions,
    )


def _extract_image_refs(line: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_MARKDOWN_IMAGE.findall(line) + _HTML_IMAGE.findall(line)))


def _is_image_only(line: str) -> bool:
    remainder = _MARKDOWN_IMAGE.sub("", line)
    remainder = _HTML_IMAGE.sub("", remainder)
    return not remainder.strip()
