"""Persistence policy for local PDF layout extraction jobs."""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Mapping


class PdfLayoutJobNotFound(FileNotFoundError):
    """Raised when a job identifier or its persisted state is unavailable."""


@dataclass(frozen=True, slots=True)
class PdfLayoutArtifactPaths:
    """Backend-owned paths required by the PDF extraction workflow."""

    source_pdf: Path
    extraction: Path
    pages: Path
    layout: Path


class PdfLayoutJobStore:
    """Own job-directory safety and the browser-facing state projection."""

    _PUBLIC_FIELDS = (
        "id", "original_filename", "status", "created_at", "started_at",
        "finished_at", "device", "language", "page_count", "phase",
        "progress_pages", "progress_total", "progress_images", "error",
    )

    def __init__(self, root: Path) -> None:
        self._root = root

    def job_dir(self, job_id: str) -> Path:
        try:
            uuid.UUID(job_id)
        except (ValueError, AttributeError, TypeError) as exc:
            raise PdfLayoutJobNotFound(job_id) from exc
        return self._root / job_id

    def source_pdf_path(self, job_id: str) -> Path:
        """Return the canonical uploaded PDF path for a validated job."""
        return self.job_dir(job_id) / "source.pdf"

    def pages_dir(self, job_id: str) -> Path:
        """Return the canonical rendered-page directory for a validated job."""
        return self.job_dir(job_id) / "pages"

    def layout_dir(self, job_id: str) -> Path:
        """Return the canonical normalized-layout directory for a validated job."""
        return self.job_dir(job_id) / "extraction" / "source" / "layout"

    def extraction_dir(self, job_id: str) -> Path:
        """Return the canonical extraction artifact directory for a validated job."""
        return self.job_dir(job_id) / "extraction"

    def artifact_paths(self, job_id: str) -> PdfLayoutArtifactPaths:
        """Expose the complete artifact policy without leaking directory layout."""
        return PdfLayoutArtifactPaths(
            source_pdf=self.source_pdf_path(job_id),
            extraction=self.extraction_dir(job_id),
            pages=self.pages_dir(job_id),
            layout=self.layout_dir(job_id),
        )

    def save_uploaded_pdf(
        self, job_id: str, source: BinaryIO, *, max_bytes: int
    ) -> int:
        """Persist the upload under the store-owned source-artifact policy."""
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")

        destination = self.source_pdf_path(job_id)
        written = 0
        try:
            with destination.open("wb") as handle:
                while chunk := source.read(1024 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise ValueError("upload exceeds maximum size")
                    handle.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return written

    def load_state(self, job_id: str) -> dict[str, Any]:
        try:
            state = json.loads(
                (self.job_dir(job_id) / "job.json").read_text(encoding="utf-8")
            )
            if not isinstance(state, dict):
                raise TypeError("persisted job state must be a JSON object")
            return state
        except (OSError, ValueError, TypeError) as exc:
            raise PdfLayoutJobNotFound(job_id) from exc

    def create_uploaded_job(
        self, job_id: str, original_filename: str, created_at: str
    ) -> dict[str, Any]:
        """Create the persisted state for a newly uploaded PDF job."""
        job_dir = self.job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=False)
        state = {
            "id": job_id,
            "original_filename": original_filename,
            "status": "uploaded",
            "created_at": created_at,
            "started_at": None,
            "finished_at": None,
            "device": None,
            "language": None,
            "page_count": None,
            "phase": "uploaded",
            "progress_pages": 0,
            "progress_total": None,
            "progress_images": 0,
            "error": None,
        }
        try:
            self.write_state(job_id, state)
        except Exception:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise
        return state

    def discard_job(self, job_id: str) -> None:
        """Remove a job and its partial artifacts after a failed upload."""
        shutil.rmtree(self.job_dir(job_id), ignore_errors=True)

    def write_state(self, job_id: str, state: dict[str, Any]) -> None:
        target = self.job_dir(job_id) / "job.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(target)

    def update_state(self, job_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        """Apply and persist one state patch at the job-store boundary."""
        state = self.load_state(job_id)
        state.update(updates)
        self.write_state(job_id, state)
        return state

    def queue_extraction(
        self, job_id: str, *, device: str, language: str
    ) -> dict[str, Any]:
        """Move an uploaded or failed job into the persisted queued state."""
        state = self.load_state(job_id)
        if state.get("status") not in {"uploaded", "failed"}:
            raise ValueError("job cannot be queued from its current status")
        state.update(
            {
                "status": "queued",
                "device": device,
                "language": language,
                "phase": "queued",
                "progress_pages": 0,
                "progress_total": None,
                "progress_images": 0,
                "error": None,
            }
        )
        self.write_state(job_id, state)
        return state

    @classmethod
    def public_state(cls, state: dict[str, Any]) -> dict[str, Any]:
        return {key: state.get(key) for key in cls._PUBLIC_FIELDS}
