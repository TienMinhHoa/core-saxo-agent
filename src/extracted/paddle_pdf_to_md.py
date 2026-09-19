#!/usr/bin/env python3
"""OCR a PDF with PaddleOCR PP-StructureV3 and export layout-aware Markdown.

The pipeline rasterizes each PDF page, detects layout blocks, OCRs text, and
keeps image/table blocks in their detected order.  PaddleOCR's own Markdown
formatter is used so images are emitted at the scale suggested by the source
page instead of being appended after all text.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

if __package__:
    from .layout_geometry import canonicalize_raw_pdf_layout
else:  # Supports ``python src/extracted/paddle_pdf_to_md.py`` as well as -m.
    from layout_geometry import canonicalize_raw_pdf_layout


def _pdf_page_count(pdf: Path) -> int | None:
    """Read the page count without loading the document into the OCR model."""
    try:
        completed = subprocess.run(
            ["pdfinfo", str(pdf)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    match = re.search(r"^Pages:\s+(\d+)", completed.stdout, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def _save_image(value: Any, destination: Path) -> None:
    """Save a Paddle image result (PIL or NumPy) without requiring OpenCV."""
    from PIL import Image

    destination.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, Image.Image):
        value.save(destination)
        return
    try:
        import numpy as np

        array = np.asarray(value)
        if array.ndim == 3 and array.shape[2] == 3:
            # Paddle/PIL commonly use RGB; Image.fromarray keeps that order.
            Image.fromarray(array).save(destination)
        else:
            Image.fromarray(array).save(destination)
    except Exception as exc:  # pragma: no cover - depends on Paddle result type
        raise TypeError(f"Unsupported Paddle image value: {type(value)!r}") from exc


def _rewrite_image_refs(markdown: str, source: str, target: str) -> str:
    """Rewrite only image references, leaving OCR text untouched."""
    source = source.replace("\\", "/")
    source_name = Path(source).name
    patterns = (
        rf'([("\s]){re.escape(source)}([)"\s])',
        rf'([("\s])(?:\./)?{re.escape(source_name)}([)"\s])',
    )
    for pattern in patterns:
        markdown = re.sub(pattern, rf"\1{target}\2", markdown)
    return markdown


def _serializable_result(result: Any) -> dict[str, Any]:
    """Get canonical source-coordinate layout data for the raw PDF page."""
    payload = result.json
    if not isinstance(payload, dict):
        raise TypeError(f"Unexpected PP-StructureV3 JSON payload: {type(payload)!r}")
    nested = payload.get("res")
    return canonicalize_raw_pdf_layout(nested if isinstance(nested, dict) else payload)


def extract(
    pdf: Path,
    output: Path,
    *,
    lang: str,
    device: str,
    tables: bool,
    max_pages: int | None = None,
    enable_mkldnn: bool = False,
) -> None:
    started = time.monotonic()
    total_pages = _pdf_page_count(pdf)
    total_label = str(total_pages) if total_pages is not None else "?"
    print(
        f"[PaddleOCR] Khởi tạo PP-StructureV3 | device={device} | "
        f"dự kiến {total_label} trang",
        flush=True,
    )
    # PaddleX defaults to ~/.paddlex, which is often read-only in managed
    # environments. Keep downloaded models/cache beside this project instead.
    cache_dir = output.parent / ".paddlex"
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_dir.resolve()))
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    try:
        if device.startswith("gpu"):
            import paddle

            cuda_devices = (
                paddle.device.cuda.device_count()
                if paddle.is_compiled_with_cuda()
                else 0
            )
            if not paddle.is_compiled_with_cuda() or cuda_devices < 1:
                raise RuntimeError(
                    "GPU was requested, but no CUDA device is visible "
                    f"(compiled_with_cuda={paddle.is_compiled_with_cuda()}, "
                    f"device_count={cuda_devices}). Install the GPU wheel and "
                    "expose the NVIDIA device to this container."
                )
        from paddleocr import PPStructureV3
    except Exception as exc:  # pragma: no cover - environment-specific
        raise RuntimeError(
            "PaddleOCR is unavailable. Install paddleocr and a compatible "
            "paddlepaddle runtime in the active virtual environment."
        ) from exc

    output.mkdir(parents=True, exist_ok=True)
    image_dir = output / "images"
    layout_dir = output / "layout"
    image_dir.mkdir(exist_ok=True)
    layout_dir.mkdir(exist_ok=True)

    pipeline = PPStructureV3(
        lang=lang,
        device=device,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        use_seal_recognition=False,
        use_table_recognition=tables,
        use_formula_recognition=False,
        use_chart_recognition=False,
        use_region_detection=False,
        format_block_content=True,
        markdown_ignore_labels=[],
        # PaddlePaddle 3.3.x has a CPU oneDNN/PIR incompatibility with some
        # PP-OCRv5 models. Keep it off by default; enable it explicitly only
        # with a known-good Paddle runtime.
        enable_mkldnn=enable_mkldnn,
    )
    print("[PaddleOCR] Model đã sẵn sàng; bắt đầu OCR...", flush=True)

    pages: list[str] = [f"# {pdf.stem} (PaddleOCR)", "", f"> Source: `{pdf.name}`", ""]
    markdown_pages: list[dict[str, Any]] = []
    try:
        for page_number, result in enumerate(pipeline.predict_iter(str(pdf)), start=1):
            page_markdown = result.markdown
            markdown = page_markdown.get("markdown_texts", "")
            images = page_markdown.get("markdown_images", {})
            for image_number, (source, value) in enumerate(images.items(), start=1):
                suffix = Path(str(source)).suffix.lower() or ".png"
                target_name = f"page-{page_number:04d}-{image_number:02d}{suffix}"
                target = image_dir / target_name
                _save_image(value, target)
                markdown = _rewrite_image_refs(
                    markdown, str(source), f"images/{target_name}"
                )

            # source_bbox is in raw-PDF-raster coordinates; block_bbox remains
            # only as Paddle's traceability field.
            (layout_dir / f"page-{page_number:04d}.json").write_text(
                json.dumps(_serializable_result(result), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            pages.extend([f"## Page {page_number}", "", markdown.strip(), "", "---", ""])
            markdown_pages.append(
                {"page": page_number, "text_length": len(markdown), "images": len(images)}
            )
            elapsed = time.monotonic() - started
            rate = page_number / elapsed if elapsed else 0.0
            remaining = (
                max(total_pages - page_number, 0) / rate if rate else None
            )
            eta = f" | còn khoảng {remaining / 60:.1f} phút" if remaining is not None else ""
            print(
                f"[PaddleOCR] Trang {page_number}/{total_label} | "
                f"{elapsed / 60:.1f} phút | {rate:.2f} trang/giây | "
                f"{len(images)} ảnh{eta}",
                flush=True,
            )
            if max_pages is not None and page_number >= max_pages:
                break
    finally:
        pipeline.close()

    (output / "document.md").write_text("\n".join(pages), encoding="utf-8")
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "source": str(pdf),
                "pages": markdown_pages,
                "engine": "PaddleOCR PP-StructureV3",
                "layout_format": {
                    "bbox_field": "source_bbox",
                    "coordinate_space": "raw_pdf_raster_pixels",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    elapsed = time.monotonic() - started
    print(
        f"[PaddleOCR] Hoàn tất {len(markdown_pages)}/{total_label} trang trong "
        f"{elapsed / 60:.1f} phút -> {output / 'document.md'}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--lang", default="en", help="PaddleOCR language (default: en)")
    parser.add_argument("--device", default="cpu", help="Inference device (default: cpu)")
    parser.add_argument("--tables", action="store_true", help="Enable table recognition")
    parser.add_argument("--max-pages", type=int, help="Only process the first N pages (useful for a smoke test)")
    parser.add_argument("--enable-mkldnn", action="store_true", help="Enable MKL-DNN acceleration (off by default for Paddle 3.3 CPU compatibility)")
    args = parser.parse_args()
    if not args.pdf.is_file():
        parser.error(f"PDF not found: {args.pdf}")
    extract(
        args.pdf,
        args.output,
        lang=args.lang,
        device=args.device,
        tables=args.tables,
        max_pages=args.max_pages,
        enable_mkldnn=args.enable_mkldnn,
    )


if __name__ == "__main__":
    main()
