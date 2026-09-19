#!/usr/bin/env python3
"""Extract a text/image PDF into page-preserving Markdown.

Uses Poppler's pdftohtml XML output because it retains the order and
coordinates of text and image blocks better than plain pdftotext.
"""
from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET


def clean_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def styled_text(element: ET.Element) -> str:
    """Render Poppler's inline b/i tags as Markdown without losing glyphs."""
    parts = [element.text or ""]
    for child in element:
        content = styled_text(child)
        if child.tag == "b":
            content = f"**{content}**"
        elif child.tag == "i":
            content = f"*{content}*"
        parts.append(content)
        parts.append(child.tail or "")
    return clean_text("".join(parts))


def text_run(element: ET.Element) -> dict[str, float | str]:
    attrs = element.attrib
    return {
        "x": float(attrs.get("left", 0)),
        "top": float(attrs.get("top", 0)),
        "width": float(attrs.get("width", 0)),
        "height": float(attrs.get("height", 0)),
        "text": styled_text(element),
    }


def same_visual_line(previous: dict[str, float | str], current: dict[str, float | str]) -> bool:
    """Join adjacent glyph runs such as the decorative O + `ne` on page 30."""
    top_delta = abs(float(current["top"]) - float(previous["top"]))
    max_height = max(float(previous["height"]), float(current["height"]))
    previous_right = float(previous["x"]) + float(previous["width"])
    horizontal_gap = float(current["x"]) - previous_right
    return top_delta <= max(4.0, max_height * 0.45) and horizontal_gap >= -2.0


def extract(pdf: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    images = output / "images"
    images.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pdf-md-") as tmp_name:
        tmp = Path(tmp_name)
        prefix = tmp / "page"
        subprocess.run(
            ["pdftohtml", "-xml", "-nodrm", str(pdf), str(prefix)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        root = ET.parse(f"{prefix}.xml").getroot()
        lines = [f"# {pdf.stem}", "", f"> Source: `{pdf.name}`", ""]

        for page in root.findall("page"):
            number = page.attrib.get("number", "?")
            lines.extend([f"## Page {number}", ""])
            block_count = 0
            page_has_content = False
            pending_text: list[dict[str, float | str]] = []
            last_text_bottom: float | None = None
            last_text_height: float | None = None

            def flush_text() -> None:
                nonlocal pending_text, last_text_bottom, last_text_height, page_has_content
                if not pending_text:
                    return
                pending_text.sort(key=lambda run: float(run["x"]))
                value = "".join(str(run["text"]) for run in pending_text).strip()
                if value:
                    top = min(float(run["top"]) for run in pending_text)
                    bottom = max(
                        float(run["top"]) + float(run["height"]) for run in pending_text
                    )
                    height = max(float(run["height"]) for run in pending_text)
                    # A large vertical gap usually means a new paragraph/heading.
                    if (
                        last_text_bottom is not None
                        and top - last_text_bottom > max(12.0, (last_text_height or height) * 1.1)
                    ):
                        lines.append("")
                    lines.append(value)
                    page_has_content = True
                    last_text_bottom = bottom
                    last_text_height = height
                pending_text = []

            for block in page:
                if block.tag == "text":
                    run = text_run(block)
                    if not run["text"]:
                        continue
                    if pending_text and not same_visual_line(pending_text[-1], run):
                        flush_text()
                    pending_text.append(run)
                elif block.tag == "image":
                    flush_text()
                    source = block.attrib.get("src")
                    if not source:
                        continue
                    source_path = Path(source)
                    # pdftohtml writes image paths relative to its XML file.
                    if not source_path.is_absolute():
                        source_path = prefix.parent / source_path
                    if not source_path.exists():
                        continue
                    block_count += 1
                    target_name = f"page-{int(number):04d}-{block_count:02d}{source_path.suffix.lower()}"
                    shutil.copy2(source_path, images / target_name)
                    if page_has_content:
                        lines.append("")
                    lines.extend([f"![Page {number} image {block_count}](images/{target_name})", ""])
                    page_has_content = True
            flush_text()
            if not page_has_content:
                lines.append("*(No extractable content on this page.)*")
                lines.append("")

    (output / "document.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    extract(args.pdf, args.output)
    print(args.output / "document.md")


if __name__ == "__main__":
    main()
