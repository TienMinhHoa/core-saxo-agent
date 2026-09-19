#!/usr/bin/env python3
"""Extract page-aware content chunks grouped by Markdown headers.

By default, level-2 headers (``##``) are treated as sections. A section ends
at the next header of the same or higher level; nested headers stay in that
section's content. ``## Page N`` markers emitted by the PDF extractor are
metadata only and are not returned as content headers.

Example:
    uv run python -m extracted.extract_header_chunks \
        output/input-vl/document.md
"""
from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PAGE_MARKER = re.compile(r"^##\s+Page\s+(\d+)\s*$", re.IGNORECASE)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
IMAGE_SOURCE = re.compile(r"(?:src|href)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


@dataclass
class _Chunk:
    header: str
    level: int
    page_start: int | None
    content_lines: list[str]
    page_end: int | None


def _clean_header(value: str) -> str:
    return re.sub(r"\s+#+\s*$", "", value).strip()


def _normalise_content(lines: list[str]) -> str:
    # Page separators are layout glue, not source content in a header chunk.
    while lines and (not lines[0].strip() or lines[0].strip() == "---"):
        lines.pop(0)
    while lines and (not lines[-1].strip() or lines[-1].strip() == "---"):
        lines.pop()
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


def extract_chunks(markdown: str, *, heading_level: int = 2) -> list[dict[str, Any]]:
    """Return section chunks with source page ranges."""
    if not 1 <= heading_level <= 6:
        raise ValueError("heading_level must be between 1 and 6")
    chunks: list[_Chunk] = []
    current_page: int | None = None
    current: _Chunk | None = None

    def finish() -> None:
        nonlocal current
        if current is None:
            return
        content = _normalise_content(current.content_lines)
        # A header with no body is still useful for review, but omit the
        # synthetic title/page headings that carry no source content.
        if content:
            chunks.append(current)
        current = None

    for raw_line in markdown.splitlines():
        page_match = PAGE_MARKER.match(raw_line)
        if page_match:
            current_page = int(page_match.group(1))
            continue

        heading_match = HEADING.match(raw_line)
        if heading_match:
            level = len(heading_match.group(1))
            title = _clean_header(heading_match.group(2))
            if level <= heading_level:
                finish()
            if level == heading_level:
                current = _Chunk(
                    header=title,
                    level=level,
                    page_start=current_page,
                    content_lines=[],
                    page_end=current_page,
                )
                continue
            # Nested headings are retained as part of the selected section.
            if current is not None:
                current.content_lines.append(raw_line)
                if current_page is not None:
                    current.page_end = current_page
            continue

        if current is not None:
            current.content_lines.append(raw_line)
            if current_page is not None and raw_line.strip() and raw_line.strip() != "---":
                current.page_end = current_page

    finish()
    return [
        {
            "header": chunk.header,
            "content": _normalise_content(chunk.content_lines),
            "page_start": chunk.page_start,
            "page_end": chunk.page_end if chunk.page_end is not None else chunk.page_start,
        }
        for chunk in chunks
    ]


def _normalise_asset_ref(value: str) -> str:
    value = value.strip()
    if value.startswith("<") and ">" in value:
        value = value[1 : value.index(">")]
    else:
        value = value.split(None, 1)[0]
    value = value.split("#", 1)[0].split("?", 1)[0].replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def _is_no_valid(record: dict[str, Any] | None) -> bool:
    if not isinstance(record, dict):
        return False
    analysis = record.get("analysis")
    return analysis == "No valid content" or (
        isinstance(analysis, dict) and analysis.get("result") == "No valid content"
    )


def _latest_vlm_results(results_path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not results_path.is_file():
        return latest
    for line_number, line in enumerate(results_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid VLM JSONL at line {line_number}: {exc}") from exc
        if not isinstance(record, dict) or not isinstance(record.get("asset"), str):
            continue
        latest[_normalise_asset_ref(record["asset"])] = record
    return latest


def _vlm_caption_block(record: dict[str, Any]) -> str:
    analysis = record.get("analysis")
    if not isinstance(analysis, dict) or _is_no_valid(record):
        return ""
    figure_number = analysis.get("figure_number")
    figure_title = analysis.get("figure_title")
    caption = analysis.get("caption")
    summary = analysis.get("summary")
    heading = " — ".join(str(value) for value in (figure_number, figure_title) if value)
    lines: list[str] = []
    if heading:
        lines.append(f"<p><strong>{html.escape(heading)}</strong></p>")
    if caption:
        lines.append(f"<p><strong>Caption:</strong> {html.escape(str(caption))}</p>")
    elif figure_title:
        lines.append(f"<p><strong>Caption:</strong> {html.escape(str(figure_title))}</p>")
    if summary:
        lines.append(f"<p><strong>Summary:</strong> {html.escape(str(summary))}</p>")
    if not lines:
        return ""
    return '<div class="vlm-figure-caption">\n' + "\n".join(lines) + "\n</div>"


def _enrich_content_images(content: str, results: dict[str, dict[str, Any]], *, remove_no_valid: bool) -> str:
    """Add VLM caption after each known image and remove rejected assets."""
    enriched: list[str] = []
    for line in content.splitlines():
        match = IMAGE_SOURCE.search(line) or MARKDOWN_IMAGE.search(line)
        if not match:
            enriched.append(line)
            continue
        source = _normalise_asset_ref(match.group(1))
        record = results.get(source)
        if _is_no_valid(record) and remove_no_valid:
            continue
        enriched.append(line)
        if record is not None:
            caption_block = _vlm_caption_block(record)
            if caption_block:
                enriched.append("")
                enriched.append(caption_block)
    return "\n".join(enriched)


def _render_markdown(
    chunks: list[dict[str, Any]],
    source: Path,
    heading_level: int,
    *,
    vlm_results: dict[str, dict[str, Any]] | None = None,
    remove_no_valid: bool = True,
) -> str:
    lines = [
        "# Header chunks",
        "",
        f"> Source: `{source}`",
        f"> Header level: {heading_level} · Chunks: {len(chunks)}",
        "",
    ]
    for index, chunk in enumerate(chunks, start=1):
        page_start, page_end = chunk["page_start"], chunk["page_end"]
        page_label = str(page_start) if page_start == page_end else f"{page_start}–{page_end}"
        lines.extend([
            f"## {index}. {chunk['header']}",
            "",
            f"**Pages:** {page_label}",
            "",
            _enrich_content_images(chunk["content"], vlm_results or {}, remove_no_valid=remove_no_valid),
            "",
            "---",
            "",
        ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_markdown", type=Path)
    parser.add_argument("--heading-level", type=int, default=2, help="Header level to chunk (default: 2 for ##)")
    parser.add_argument("--json-output", type=Path, help="Default: <input-stem>-header-chunks.json")
    parser.add_argument("--markdown-output", type=Path, help="Default: <input-stem>-header-chunks.md")
    parser.add_argument("--vlm-results", type=Path, help="Default: <input-dir>/vlm-figures/figure-vlm-results.jsonl")
    parser.add_argument("--keep-no-valid", action="store_true", help="Keep images whose VLM result is No valid content")
    args = parser.parse_args()
    if not args.input_markdown.is_file():
        parser.error(f"Markdown not found: {args.input_markdown}")
    if not 1 <= args.heading_level <= 6:
        parser.error("--heading-level must be between 1 and 6")

    chunks = extract_chunks(args.input_markdown.read_text(encoding="utf-8"), heading_level=args.heading_level)
    json_output = args.json_output or args.input_markdown.with_name(f"{args.input_markdown.stem}-header-chunks.json")
    markdown_output = args.markdown_output or args.input_markdown.with_name(f"{args.input_markdown.stem}-header-chunks.md")
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    vlm_results_path = args.vlm_results or args.input_markdown.parent / "vlm-figures" / "figure-vlm-results.jsonl"
    try:
        vlm_results = _latest_vlm_results(vlm_results_path)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    markdown_output.write_text(
        _render_markdown(
            chunks,
            args.input_markdown,
            args.heading_level,
            vlm_results=vlm_results,
            remove_no_valid=not args.keep_no_valid,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {len(chunks)} chunks to {json_output} and {markdown_output}")


if __name__ == "__main__":
    main()
