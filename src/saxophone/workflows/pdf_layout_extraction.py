"""Application workflow for running one PDF layout extraction job."""

from __future__ import annotations

import importlib
import threading
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from saxophone.workflows.pdf_layout_jobs import PdfLayoutArtifactPaths


def run_extraction(
    job_id: str,
    *,
    artifact_paths: Callable[[str], PdfLayoutArtifactPaths],
    load_state: Callable[[str], dict[str, Any]],
    write_state: Callable[[str, dict[str, Any]], None],
    render_pages: Callable[[Path, Path], list[str]],
    extraction_lock: threading.Lock,
) -> None:
    """Run the legacy OCR adapter and persist the workflow state transitions."""
    state = load_state(job_id)
    state.update(
        {
            "status": "running",
            "started_at": _timestamp(),
            "phase": "initializing",
            "progress_pages": 0,
            "progress_total": None,
            "progress_images": 0,
            "error": None,
        }
    )
    write_state(job_id, state)
    paths = artifact_paths(job_id)
    source_pdf = paths.source_pdf
    extraction_root = paths.extraction
    rendered_pages = paths.pages
    try:
        legacy_pipeline = importlib.import_module("extracted.parse_pdf_2_md")
        check_gpu = legacy_pipeline.check_gpu
        create_source_coordinate_pipeline = legacy_pipeline.create_source_coordinate_pipeline
        pdf_page_count = legacy_pipeline.pdf_page_count
        save_one_pdf = legacy_pipeline.save_one_pdf

        with extraction_lock:
            check_gpu(str(state["device"]))
            total_pages = pdf_page_count(source_pdf)
            pipeline = create_source_coordinate_pipeline(
                lang=str(state["language"]), device=str(state["device"])
            )
            try:
                state = load_state(job_id)
                state.update({"phase": "extracting", "progress_total": total_pages})
                write_state(job_id, state)

                def report_progress(page: int, total: int | None, images: int) -> None:
                    current_state = load_state(job_id)
                    current_state.update(
                        {
                            "phase": "extracting",
                            "progress_pages": page,
                            "progress_total": total,
                            "progress_images": images,
                        }
                    )
                    write_state(job_id, current_state)

                save_one_pdf(
                    pipeline,
                    source_pdf,
                    extraction_root,
                    on_progress=report_progress,
                )
            finally:
                pipeline.close()
            state = load_state(job_id)
            state.update({"phase": "rendering"})
            write_state(job_id, state)
            page_images = render_pages(source_pdf, rendered_pages)

        state = load_state(job_id)
        state.update(
            {
                "status": "completed",
                "finished_at": _timestamp(),
                "page_count": len(page_images),
                "phase": "completed",
                "progress_pages": len(page_images),
                "progress_total": len(page_images),
                "error": None,
            }
        )
        write_state(job_id, state)
    except Exception as exc:  # pragma: no cover - OCR runtime is environment-specific
        state = load_state(job_id)
        state.update(
            {
                "status": "failed",
                "finished_at": _timestamp(),
                "phase": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=12),
            }
        )
        write_state(job_id, state)


def _timestamp() -> str:
    """Return the UTC timestamp used by the job state contract."""
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
