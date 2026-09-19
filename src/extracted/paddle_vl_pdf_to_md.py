#!/usr/bin/env python3
"""Extract a PDF to Markdown with PaddleOCR-VL, not PP-StructureV3.

PaddleOCR-VL uses a vision-language model for document understanding.  The
output directory contains one combined Markdown document, image assets emitted
by PaddleOCR-VL, and the original per-page result JSON for inspection.

Example:
    uv run python -m extracted.paddle_vl_pdf_to_md \
        docs/input.pdf -o output/input-vl --device gpu:0
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


def _pdf_page_count(pdf: Path) -> int | None:
    """Return the PDF page count when Poppler's ``pdfinfo`` is available."""
    try:
        completed = subprocess.run(
            ["pdfinfo", str(pdf)], check=True, capture_output=True, text=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    match = re.search(r"^Pages:\s+(\d+)", completed.stdout, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def _save_image(value: Any, destination: Path) -> None:
    """Save a PIL or NumPy image returned in ``markdown_images``."""
    from PIL import Image

    destination.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, Image.Image):
        value.save(destination)
        return

    try:
        import numpy as np

        Image.fromarray(np.asarray(value)).save(destination)
    except Exception as exc:  # pragma: no cover - depends on Paddle result type
        raise TypeError(f"Unsupported PaddleOCR-VL image value: {type(value)!r}") from exc


def _rewrite_image_refs(markdown: str, source: str, target: str) -> str:
    """Point only Markdown image URLs at the assets saved by this script."""
    source = source.replace("\\", "/")
    source_name = Path(source).name
    patterns = (
        rf'([(\"\s]){re.escape(source)}([)\"\s])',
        rf'([(\"\s])(?:\./)?{re.escape(source_name)}([)\"\s])',
    )
    for pattern in patterns:
        markdown = re.sub(pattern, rf"\1{target}\2", markdown)
    return markdown


def _result_json(result: Any) -> dict[str, Any]:
    """Return a JSON-serializable per-page PaddleOCR-VL result payload."""
    payload = result.json
    if not isinstance(payload, dict):
        raise TypeError(f"Unexpected PaddleOCR-VL JSON payload: {type(payload)!r}")
    return payload


def _check_gpu(device: str) -> None:
    if not device.startswith("gpu"):
        return
    try:
        import paddle

        device_count = (
            paddle.device.cuda.device_count() if paddle.is_compiled_with_cuda() else 0
        )
    except Exception as exc:  # pragma: no cover - runtime-specific
        raise RuntimeError("PaddlePaddle is required when using a GPU device.") from exc
    if device_count < 1:
        raise RuntimeError(
            "GPU was requested, but no CUDA device is visible. "
            "Use --device cpu or install a CUDA-enabled PaddlePaddle runtime."
        )


def extract(
    pdf: Path,
    output: Path,
    *,
    device: str,
    pipeline_version: str,
    vl_rec_model_name: str | None,
    vl_rec_model_dir: Path | None,
    vl_rec_backend: str | None,
    max_new_tokens: int | None,
    max_pages: int | None,
) -> None:
    """Run PaddleOCR-VL and write its Markdown, assets, and page JSON."""
    # PaddleX normally caches models under ~/.paddlex.  Keep that cache next
    # to the output so this command also works in managed/read-only homes.
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str((output.parent / ".paddlex").resolve()))
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    try:
        from paddleocr import PaddleOCRVL
    except Exception as exc:  # pragma: no cover - installation-specific
        raise RuntimeError(
            "PaddleOCR-VL is unavailable. Install a recent paddleocr package and "
            "a compatible paddlepaddle runtime."
        ) from exc

    _check_gpu(device)
    output.mkdir(parents=True, exist_ok=True)
    image_dir = output / "images"
    layout_dir = output / "layout"
    image_dir.mkdir(exist_ok=True)
    layout_dir.mkdir(exist_ok=True)

    total_pages = _pdf_page_count(pdf)
    total_label = str(total_pages) if total_pages is not None else "?"
    print(
        f"[PaddleOCR-VL] Initializing {pipeline_version} on {device} "
        f"for {total_label} page(s)...",
        flush=True,
    )
    pipeline = PaddleOCRVL(
        pipeline_version=pipeline_version,
        device=device,
        vl_rec_model_name=vl_rec_model_name,
        vl_rec_model_dir=str(vl_rec_model_dir) if vl_rec_model_dir else None,
        vl_rec_backend=vl_rec_backend,
        # Keep source coordinates stable for the JSON files.  The source PDF
        # pages are already rasterized by PaddleOCR-VL internally.
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_layout_detection=True,
        format_block_content=True,
        markdown_ignore_labels=[],
    )

    started = time.monotonic()
    markdown_parts = [f"# {pdf.stem} (PaddleOCR-VL)", "", f"> Source: `{pdf.name}`", ""]
    pages: list[dict[str, Any]] = []
    try:
        for page_number, result in enumerate(
            pipeline.predict_iter(str(pdf), max_new_tokens=max_new_tokens), start=1
        ):
            markdown_info = result.markdown
            markdown = markdown_info.get("markdown_texts", "")
            images = markdown_info.get("markdown_images", {})
            for image_number, (source, value) in enumerate(images.items(), start=1):
                suffix = Path(str(source)).suffix.lower() or ".png"
                filename = f"page-{page_number:04d}-{image_number:02d}{suffix}"
                _save_image(value, image_dir / filename)
                markdown = _rewrite_image_refs(markdown, str(source), f"images/{filename}")

            (layout_dir / f"page-{page_number:04d}.json").write_text(
                json.dumps(_result_json(result), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            markdown_parts.extend([f"## Page {page_number}", "", markdown.strip(), "", "---", ""])
            pages.append(
                {
                    "page": page_number,
                    "text_length": len(markdown),
                    "images": len(images),
                }
            )
            print(
                f"[PaddleOCR-VL] Page {page_number}/{total_label} | "
                f"{len(images)} image(s)",
                flush=True,
            )
            if max_pages is not None and page_number >= max_pages:
                break
    finally:
        pipeline.close()

    markdown_path = output / "document.md"
    markdown_path.write_text("\n".join(markdown_parts), encoding="utf-8")
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "source": str(pdf),
                "output_markdown": str(markdown_path),
                "output_layout_dir": str(layout_dir),
                "engine": "PaddleOCR-VL",
                "pipeline_version": pipeline_version,
                "vl_rec_model_name": vl_rec_model_name,
                "vl_rec_model_dir": str(vl_rec_model_dir) if vl_rec_model_dir else None,
                "vl_rec_backend": vl_rec_backend,
                "pages": pages,
                "elapsed_seconds": round(time.monotonic() - started, 2),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"[PaddleOCR-VL] Completed {len(pages)}/{total_label} page(s) -> {markdown_path}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Source PDF")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu", help="Inference device, e.g. cpu or gpu:0")
    parser.add_argument(
        "--pipeline-version", default="v1.6", choices=("v1", "v1.5", "v1.6")
    )
    parser.add_argument("--vl-rec-model-name", help="Optional PaddleOCR-VL recognition model name")
    parser.add_argument("--vl-rec-model-dir", type=Path, help="Optional local PaddleOCR-VL model directory")
    parser.add_argument(
        "--vl-rec-backend",
        choices=("native", "vllm-server", "sglang-server", "fastdeploy-server", "mlx-vlm-server", "llama-cpp-server"),
        help="VLM backend; PaddleOCR chooses its default when omitted",
    )
    parser.add_argument("--max-new-tokens", type=int, help="Limit VLM output tokens per page")
    parser.add_argument("--max-pages", type=int, help="Process only the first N pages")
    args = parser.parse_args()
    if not args.pdf.is_file():
        parser.error(f"PDF not found: {args.pdf}")
    if args.max_pages is not None and args.max_pages < 1:
        parser.error("--max-pages must be at least 1")
    if args.max_new_tokens is not None and args.max_new_tokens < 1:
        parser.error("--max-new-tokens must be at least 1")

    extract(
        args.pdf,
        args.output,
        device=args.device,
        pipeline_version=args.pipeline_version,
        vl_rec_model_name=args.vl_rec_model_name,
        vl_rec_model_dir=args.vl_rec_model_dir,
        vl_rec_backend=args.vl_rec_backend,
        max_new_tokens=args.max_new_tokens,
        max_pages=args.max_pages,
    )


if __name__ == "__main__":
    main()
