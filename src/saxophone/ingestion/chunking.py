"""Deterministic conversion from extracted Markdown to source chunks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .models import IngestionSourceChunk

_PAGE_MARKER = re.compile(r"^##\s+Page\s+(\d+)\s*$", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass
class _PendingChunk:
    heading: str
    page_start: int | None
    page_end: int | None
    lines: list[str]


def build_source_chunks(
    markdown: str,
    *,
    document_ref: str,
    source_version: str,
    access_scope: str,
    heading_level: int = 2,
) -> tuple[IngestionSourceChunk, ...]:
    """Build stable, pre-embedding chunks from selected Markdown headings.

    Page markers are provenance metadata and nested headings remain source text;
    no provider, LLM, or embedding behavior is involved in this boundary.
    """
    if not isinstance(markdown, str):
        raise ValueError("markdown must be a string")
    if not 1 <= heading_level <= 6:
        raise ValueError("heading_level must be between 1 and 6")

    chunks: list[tuple[str, int | None, int | None, str]] = []
    current_page: int | None = None
    current: _PendingChunk | None = None

    def finish() -> None:
        nonlocal current
        if current is None:
            return
        content = _normalize_content(current.lines)
        if content:
            chunks.append((current.heading, current.page_start, current.page_end, content))
        current = None

    for raw_line in markdown.splitlines():
        page_match = _PAGE_MARKER.match(raw_line)
        if page_match:
            current_page = int(page_match.group(1))
            if current is not None:
                current.page_end = current_page
            continue

        heading_match = _HEADING.match(raw_line)
        if heading_match:
            level = len(heading_match.group(1))
            if level <= heading_level:
                finish()
            if level == heading_level:
                current = _PendingChunk(
                    heading=_clean_heading(heading_match.group(2)),
                    page_start=current_page,
                    page_end=current_page,
                    lines=[],
                )
                continue
            if current is not None:
                current.lines.append(raw_line)
            continue

        if current is not None:
            current.lines.append(raw_line)
            if current_page is not None and raw_line.strip():
                current.page_end = current_page
    finish()

    return tuple(
        IngestionSourceChunk(
            chunk_id=_chunk_id(document_ref, source_version, index, heading, content),
            document_ref=document_ref,
            source_version=source_version,
            search_text=content,
            access_scope=access_scope,
            metadata={
                "heading": heading,
                "heading_level": heading_level,
                "page_start": page_start,
                "page_end": page_end,
            },
        )
        for index, (heading, page_start, page_end, content) in enumerate(chunks)
    )


def _clean_heading(value: str) -> str:
    return re.sub(r"\s+#+\s*$", "", value).strip()


def _normalize_content(lines: list[str]) -> str:
    cleaned: list[str] = []
    blank_pending = False
    for line in lines:
        if line.strip() == "---":
            continue
        if not line.strip():
            blank_pending = True
            continue
        if blank_pending and cleaned:
            cleaned.append("")
        blank_pending = False
        cleaned.append(line.rstrip())
    return "\n".join(cleaned).strip()


def _chunk_id(
    document_ref: str,
    source_version: str,
    index: int,
    heading: str,
    content: str,
) -> str:
    digest = hashlib.sha256(f"{heading}\n{content}".encode("utf-8")).hexdigest()[:16]
    return f"{document_ref}:{source_version}:{index}:{digest}"
