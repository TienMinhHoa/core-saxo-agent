#!/usr/bin/env python3
"""Process every PDF in a directory with PaddleOCR PP-StructureV3."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

# Keep PaddleX's cache inside the project; managed home directories may be
# read-only. Set this before importing paddleocr/paddlex.
# This file lives in <project>/src/extracted/, so parents[2] is the project
# root.  Keeping this at parents[1] accidentally creates a second cache in
# <project>/src/.paddlex instead of reusing <project>/.paddlex.
PROJECT_DIR = Path(__file__).resolve().parents[2]
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(PROJECT_DIR / ".paddlex"))
# Avoid a network availability probe on every startup.  Missing model files
# are still downloaded normally when needed.
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

import paddle
from paddleocr import PPStructureV3
from tqdm import tqdm

if __package__:
    from .layout_geometry import canonicalize_raw_pdf_layout
else:  # Supports ``python src/extracted/parse_pdf_2_md.py`` as well as -m.
    from layout_geometry import canonicalize_raw_pdf_layout


def pdf_page_count(pdf_path: Path) -> int | None:
    try:
        stdout = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    for line in stdout.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def check_gpu(device: str) -> None:
    if not device.startswith("gpu"):
        return
    try:
        count = paddle.device.cuda.device_count() if paddle.is_compiled_with_cuda() else 0
    except Exception:
        count = 0
    if not paddle.is_compiled_with_cuda() or count < 1:
        raise RuntimeError(
            "GPU được yêu cầu nhưng không có CUDA device khả dụng: "
            f"compiled_with_cuda={paddle.is_compiled_with_cuda()}, device_count={count}. "
            "Hãy expose NVIDIA GPU cho container/server hoặc chạy với --device cpu."
        )


def serializable_layout(result: Any) -> dict[str, Any]:
    """Return a source-coordinate JSON payload with OCR text and layout boxes.

    In PP-StructureV3, the useful text-to-position mapping is normally in
    ``parsing_res_list``: each block contains ``block_content`` together with
    ``block_bbox`` (and label, order, and confidence metadata).  Paddle wraps
    that data in a top-level ``res`` field in some releases, so unwrap it for
    a stable per-page output format.
    """
    payload = result.json
    if not isinstance(payload, dict):
        raise TypeError(f"Unexpected PP-StructureV3 JSON payload: {type(payload)!r}")
    nested = payload.get("res")
    raw_page = nested if isinstance(nested, dict) else payload
    return canonicalize_raw_pdf_layout(raw_page)


def create_source_coordinate_pipeline(*, lang: str, device: str) -> PPStructureV3:
    """Create OCR that preserves the original PDF raster coordinate space."""
    return PPStructureV3(
        lang=lang,
        device=device,
        # The viewer is a raster of the original PDF.  Paddle does not export
        # the inverse transform for either operation, so either one would make
        # block_bbox unsafe for an overlay.
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
    )


def save_one_pdf(
    pipeline: PPStructureV3,
    pdf_path: Path,
    output_root: Path,
    on_progress: Callable[[int, int | None, int], None] | None = None,
) -> dict:
    """OCR one PDF and save Markdown, images, and per-page layout JSON."""
    file_started = time.monotonic()
    total_pages = pdf_page_count(pdf_path)
    total_label = str(total_pages) if total_pages is not None else "?"
    file_output = output_root / pdf_path.stem
    file_output.mkdir(parents=True, exist_ok=True)
    layout_dir = file_output / "layout"
    layout_dir.mkdir(exist_ok=True)
    print(
        f"\n[FILE] {pdf_path.name} | {total_label} trang | output={file_output}",
        flush=True,
    )

    markdown_pages: list[dict] = []
    markdown_images: list[dict] = []
    page_results = pipeline.predict_iter(input=str(pdf_path))
    with tqdm(
        page_results,
        total=total_pages,
        desc=f"{pdf_path.name[:28]:28}",
        unit="page",
        dynamic_ncols=True,
    ) as progress:
        for page_number, result in enumerate(progress, start=1):
            md_info = result.markdown
            page_images = md_info.get("markdown_images", {})

            # Preserve canonical source geometry instead of inferring it from
            # Markdown.  source_bbox is in the unmodified PDF page raster;
            # block_bbox remains Paddle's original field for traceability.
            # See layout/page-XXXX.json -> parsing_res_list:
            #   block_content: recognized text
            #   source_bbox: [x1, y1, x2, y2] in raw PDF page pixels
            #   block_label/block_order: detected element type and read order
            (layout_dir / f"page-{page_number:04d}.json").write_text(
                json.dumps(serializable_layout(result), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            markdown_pages.append(md_info)
            markdown_images.append(page_images)
            progress.set_postfix(page=page_number, images=len(page_images))
            if on_progress is not None:
                on_progress(page_number, total_pages, len(page_images))

    print(f"[MD] {pdf_path.name}: đang ghép Markdown...", flush=True)
    combined_result = pipeline.concatenate_markdown_pages(markdown_pages)
    if isinstance(combined_result, str):
        combined_markdown = combined_result
    else:
        combined_markdown = combined_result.get("markdown_texts", "")

    md_path = file_output / f"{pdf_path.stem}.md"
    md_path.write_text(combined_markdown, encoding="utf-8")

    image_items = [
        (relative_path, image)
        for page_images in markdown_images
        for relative_path, image in page_images.items()
    ]
    with tqdm(
        image_items,
        desc=f"Images {pdf_path.name[:22]:22}",
        unit="image",
        dynamic_ncols=True,
    ) as progress:
        for relative_path, image in progress:
            image_path = file_output / relative_path
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(image_path)

    elapsed = time.monotonic() - file_started
    manifest = {
        "source": str(pdf_path),
        "output_markdown": str(md_path),
        "output_layout_dir": str(layout_dir),
        "layout_format": {
            "per_page": "layout/page-XXXX.json",
            "blocks_path": "parsing_res_list",
            "text_field": "block_content",
            "bbox_field": "source_bbox",
            "coordinate_space": "raw_pdf_raster_pixels; top-left origin; see width and height in each JSON file",
        },
        "pages": len(markdown_pages),
        "images": len(image_items),
        "elapsed_seconds": round(elapsed, 2),
    }
    (file_output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"[DONE] {pdf_path.name}: {len(markdown_pages)}/{total_label} trang, "
        f"{len(image_items)} ảnh, {elapsed / 60:.1f} phút",
        flush=True,
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR all PDFs in a directory with PaddleOCR PP-StructureV3."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=PROJECT_DIR / "docs",
        help="Folder containing PDFs (default: project/docs)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_DIR / "output",
        help="Output folder (default: project/output)",
    )
    parser.add_argument("--lang", default="en")
    parser.add_argument("--device", default="gpu:0", help="gpu:0 or cpu")
    args = parser.parse_args()

    pdfs = sorted(args.input_dir.glob("*.pdf"))
    if not pdfs:
        parser.error(f"Không tìm thấy PDF trong {args.input_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    print(f"[0/3] Tìm thấy {len(pdfs)} PDF trong {args.input_dir}", flush=True)
    check_gpu(args.device)
    print(f"[1/3] Khởi tạo PP-StructureV3 trên {args.device}...", flush=True)
    pipeline = create_source_coordinate_pipeline(lang=args.lang, device=args.device)
    print("[2/3] Model đã sẵn sàng; bắt đầu xử lý batch", flush=True)

    summaries = []
    failures = []
    try:
        for file_number, pdf_path in enumerate(pdfs, start=1):
            print(f"[BATCH] File {file_number}/{len(pdfs)}", flush=True)
            try:
                summaries.append(save_one_pdf(pipeline, pdf_path, args.output_dir))
            except Exception as exc:
                failures.append({"source": str(pdf_path), "error": repr(exc)})
                print(f"[ERROR] {pdf_path.name}: {exc}", flush=True)
    finally:
        pipeline.close()

    batch_manifest = {
        "input_dir": str(args.input_dir),
        "output_dir": str(args.output_dir),
        "files_found": len(pdfs),
        "files_completed": len(summaries),
        "failures": failures,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "files": summaries,
    }
    (args.output_dir / "batch-manifest.json").write_text(
        json.dumps(batch_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"[3/3] Batch hoàn tất: {len(summaries)}/{len(pdfs)} file, "
        f"tổng {batch_manifest['elapsed_seconds'] / 60:.1f} phút",
        flush=True,
    )
    if failures:
        print(
            f"[WARN] Có {len(failures)} file lỗi; xem "
            f"{args.output_dir / 'batch-manifest.json'}",
            flush=True,
        )


if __name__ == "__main__":
    main()
