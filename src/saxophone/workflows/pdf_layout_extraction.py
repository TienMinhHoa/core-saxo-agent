"""Application workflow for running one PDF layout extraction job."""

from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from saxophone.extraction.paddle_vllm import (
    PaddleVllmLayoutExtractor,
    paddle_vllm_extractor_from_environment,
)
from saxophone.workflows import PdfLayoutArtifactPaths


def load_layout_pages(
    job_id: str,
    *,
    load_completed_state: Callable[[str], dict[str, Any]],
    public_state: Callable[[dict[str, Any]], dict[str, Any]],
    layout_path: Callable[[str], Path],
    read_pages: Callable[[Path, Callable[[int], str]], list[dict[str, Any]]],
    page_url: Callable[[int], str],
) -> dict[str, Any]:
    """Build the completed-layout response through workflow-owned policies."""
    state = load_completed_state(job_id)
    return {
        "job": public_state(state),
        "pages": read_pages(layout_path(job_id), page_url),
    }


def start_extraction(
    job_id: str,
    *,
    artifact_paths: Callable[[str], PdfLayoutArtifactPaths],
    update_state: Callable[[str, dict[str, Any]], dict[str, Any]],
    render_pages: Callable[[Path, Path], list[str]],
    extraction_lock: threading.Lock,
    thread_factory: Callable[..., threading.Thread] = threading.Thread,
    extractor_factory: Callable[[], PaddleVllmLayoutExtractor] | None = None,
) -> None:
    """Launch one extraction workflow without exposing thread wiring to HTTP."""
    worker_kwargs: dict[str, Any] = {
        "artifact_paths": artifact_paths,
        "update_state": update_state,
        "render_pages": render_pages,
        "extraction_lock": extraction_lock,
    }
    if extractor_factory is not None:
        worker_kwargs["extractor_factory"] = extractor_factory
    worker = thread_factory(
        target=run_extraction,
        args=(job_id,),
        kwargs=worker_kwargs,
        daemon=True,
    )
    worker.start()


def run_extraction(
    job_id: str,
    *,
    artifact_paths: Callable[[str], PdfLayoutArtifactPaths],
    update_state: Callable[[str, dict[str, Any]], dict[str, Any]],
    render_pages: Callable[[Path, Path], list[str]],
    extraction_lock: threading.Lock,
    extractor_factory: Callable[[], PaddleVllmLayoutExtractor] = paddle_vllm_extractor_from_environment,
) -> None:
    """Run remote PaddleOCR-VL and persist the workflow state transitions."""
    state = update_state(
        job_id,
        {
            "status": "running",
            "started_at": _timestamp(),
            "phase": "initializing",
            "progress_pages": 0,
            "progress_total": None,
            "progress_images": 0,
            "error": None,
        },
    )
    try:
        paths = artifact_paths(job_id)
        extractor = extractor_factory()
        with extraction_lock:
            update_state(job_id, {"phase": "extracting"})

            def report_progress(page: int, total: int | None, images: int) -> None:
                update_state(
                    job_id,
                    {
                        "phase": "extracting",
                        "progress_pages": page,
                        "progress_total": total,
                        "progress_images": images,
                    },
                )

            report = extractor.extract(
                paths.source_pdf,
                paths.extraction,
                on_progress=report_progress,
            )
            update_state(job_id, {"phase": "rendering"})
            page_images = render_pages(paths.source_pdf, paths.pages)
        page_count = len(page_images) or report.page_count
        update_state(
            job_id,
            {
                "status": "completed",
                "finished_at": _timestamp(),
                "page_count": page_count,
                "phase": "completed",
                "progress_pages": page_count,
                "progress_total": page_count,
                "progress_images": report.image_count,
                "error": None,
            },
        )
    except Exception as exc:  # pragma: no cover - OCR runtime is environment-specific
        update_state(
            job_id,
            {
                "status": "failed",
                "finished_at": _timestamp(),
                "phase": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=12),
            },
        )


def _timestamp() -> str:
    """Return the UTC timestamp used by the job state contract."""
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
