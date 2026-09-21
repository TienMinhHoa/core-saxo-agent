"""Compatibility adapter for the legacy local PDF layout extractor."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from saxophone.workflows.pdf_layout_jobs import PdfLayoutArtifactPaths


def run_legacy_extraction(
    state: dict[str, Any],
    *,
    job_id: str,
    artifact_paths: Callable[[str], "PdfLayoutArtifactPaths"],
    update_state: Callable[[str, dict[str, Any]], dict[str, Any]],
    render_pages: Callable[[Path, Path], list[str]],
    extraction_lock: Lock,
    timestamp: Callable[[], str],
) -> None:
    """Run the legacy provider outside workflow orchestration."""
    legacy_pipeline = importlib.import_module("extracted.parse_pdf_2_md")
    check_gpu = legacy_pipeline.check_gpu
    create_source_coordinate_pipeline = legacy_pipeline.create_source_coordinate_pipeline
    pdf_page_count = legacy_pipeline.pdf_page_count
    save_one_pdf = legacy_pipeline.save_one_pdf

    paths = artifact_paths(job_id)
    with extraction_lock:
        check_gpu(str(state["device"]))
        total_pages = pdf_page_count(paths.source_pdf)
        pipeline = create_source_coordinate_pipeline(
            lang=str(state["language"]), device=str(state["device"])
        )
        try:
            update_state(job_id, {"phase": "extracting", "progress_total": total_pages})

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

            save_one_pdf(
                pipeline,
                paths.source_pdf,
                paths.extraction,
                on_progress=report_progress,
            )
        finally:
            pipeline.close()
        update_state(job_id, {"phase": "rendering"})
        page_images = render_pages(paths.source_pdf, paths.pages)

    update_state(
        job_id,
        {
            "status": "completed",
            "finished_at": timestamp(),
            "page_count": len(page_images),
            "phase": "completed",
            "progress_pages": len(page_images),
            "progress_total": len(page_images),
            "error": None,
        },
    )
