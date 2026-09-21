"""Local PDF page rasterization adapter."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


def render_pdf_pages(source_pdf: Path, page_dir: Path) -> list[str]:
    """Rasterize PDF pages with the local Poppler adapter."""
    if shutil.which("pdftoppm") is None:
        raise RuntimeError("Thiếu lệnh pdftoppm. Cài poppler-utils để render trang PDF.")
    page_dir.mkdir(parents=True, exist_ok=True)
    prefix = page_dir / "page"
    subprocess.run(
        ["pdftoppm", "-png", "-r", "144", str(source_pdf), str(prefix)],
        check=True,
        capture_output=True,
        text=True,
    )
    return [path.name for path in sorted(page_dir.glob("page-*.png"), key=_page_number)]


def _page_number(path: Path) -> int:
    match = re.search(r"-(\d+)\.png$", path.name)
    return int(match.group(1)) if match else 0
