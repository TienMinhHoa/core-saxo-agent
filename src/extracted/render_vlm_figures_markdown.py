#!/usr/bin/env python3
"""Render DeepSeek figure results as a side-by-side Markdown review.

The generated document uses a small HTML table because ordinary Markdown has
no portable two-column layout. Each row has the extracted image on the left
and its VLM result on the right.

Example:
    uv run python -m extracted.render_vlm_figures_markdown \
        output/input-vl
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
from pathlib import Path
from typing import Any


RESULT_ID = re.compile(r"^page-(\d+):")


def _read_results(path: Path) -> list[dict[str, Any]]:
    """Read JSONL, keeping the newest record for each candidate id."""
    latest: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number} of {path}: {exc}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("id"), str):
            continue
        latest[value["id"]] = value
    return sorted(latest.values(), key=_result_sort_key)


def _result_sort_key(result: dict[str, Any]) -> tuple[int, str]:
    page_match = RESULT_ID.match(str(result.get("id", "")))
    page = int(page_match.group(1)) if page_match else int(result.get("page", 10**9))
    return page, str(result.get("asset", ""))


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _line(label: str, value: Any) -> str:
    if value is None or value == "" or value == []:
        return ""
    return f"<p><strong>{_escape(label)}:</strong> {_escape(value)}</p>"


def _analysis_html(analysis: Any) -> str:
    if not isinstance(analysis, dict):
        return _line("Result", analysis)
    if analysis.get("result") == "No valid content":
        return '<p><strong>No valid content</strong></p>'

    chunks = []
    figure_number = analysis.get("figure_number")
    figure_title = analysis.get("figure_title")
    if figure_number or figure_title:
        heading = " — ".join(str(value) for value in (figure_number, figure_title) if value)
        chunks.append(f"<h3>{_escape(heading)}</h3>")
    chunks.extend(
        item
        for item in (
            _line("Caption", analysis.get("caption")),
            _line("Caption source", analysis.get("caption_source")),
            _line("Asset type", analysis.get("asset_type")),
            _line("Content transcription", analysis.get("content_transcription")),
            _line("Summary", analysis.get("summary")),
            _line("Figure count", analysis.get("figure_count")),
            _line("Confidence", analysis.get("confidence")),
            _line("Uncertainties", " | ".join(map(str, analysis.get("uncertainties", [])))),
        )
        if item
    )
    subfigures = analysis.get("subfigures")
    if isinstance(subfigures, list) and subfigures:
        chunks.append("<p><strong>Subfigures:</strong></p><ul>")
        for subfigure in subfigures:
            if not isinstance(subfigure, dict):
                continue
            description = subfigure.get("description") or ""
            label = subfigure.get("label")
            prefix = f"{label}: " if label else ""
            chunks.append(f"<li>{_escape(prefix + str(description))}</li>")
        chunks.append("</ul>")
    return "\n".join(chunks) or '<p><em>No structured VLM content.</em></p>'


def render(
    extraction_dir: Path,
    results_path: Path | None = None,
    destination: Path | None = None,
    *,
    include_no_valid: bool = True,
) -> Path:
    """Render result records into a side-by-side Markdown file."""
    results_path = results_path or extraction_dir / "vlm-figures" / "figure-vlm-results.jsonl"
    destination = destination or extraction_dir / "vlm-figures" / "figure-review.md"
    if not results_path.is_file():
        raise FileNotFoundError(f"Results JSONL not found: {results_path}")
    results = _read_results(results_path)
    rows: list[str] = []
    included = 0
    skipped = 0
    for result in results:
        analysis = result.get("analysis")
        if not include_no_valid and isinstance(analysis, dict) and analysis.get("result") == "No valid content":
            skipped += 1
            continue
        asset_value = result.get("asset")
        if not isinstance(asset_value, str):
            skipped += 1
            continue
        asset_path = extraction_dir / asset_value
        if not asset_path.is_file():
            skipped += 1
            continue
        relative_asset = os.path.relpath(asset_path, destination.parent).replace(os.sep, "/")
        page = result.get("page", "?")
        image_alt = f"Page {page} — {Path(asset_value).name}"
        header = f"Page {page} · {Path(asset_value).name}"
        rows.append(
            "<tr>\n"
            f'  <td style="width:48%; vertical-align:top; text-align:center; padding:12px;">'
            f'<a href="{_escape(relative_asset)}"><img src="{_escape(relative_asset)}" alt="{_escape(image_alt)}" style="max-width:100%; height:auto;"></a>'
            "</td>\n"
            f'  <td style="width:52%; vertical-align:top; padding:12px;">'
            f"<h2>{_escape(header)}</h2>\n{_analysis_html(analysis)}"
            "</td>\n</tr>"
        )
        included += 1

    destination.parent.mkdir(parents=True, exist_ok=True)
    document = [
        "# PaddleOCR-VL / DeepSeek Figure Review",
        "",
        f"> Source extraction: `{extraction_dir}`",
        f"> Records read: {len(results)} · Included: {included} · Skipped: {skipped}",
        "",
        '<table style="width:100%; table-layout:fixed;">',
        *rows,
        "</table>",
        "",
    ]
    destination.write_text("\n".join(document), encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extraction_dir", type=Path)
    parser.add_argument("-i", "--results", type=Path, help="Input JSONL (default: <extraction-dir>/vlm-figures/figure-vlm-results.jsonl)")
    parser.add_argument("-o", "--output", type=Path, help="Output Markdown (default: <extraction-dir>/vlm-figures/figure-review.md)")
    parser.add_argument("--only-valid", action="store_true", help="Omit records whose VLM result is No valid content")
    args = parser.parse_args()
    try:
        output = render(args.extraction_dir, args.results, args.output, include_no_valid=not args.only_valid)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Wrote side-by-side figure review: {output}")


if __name__ == "__main__":
    main()
