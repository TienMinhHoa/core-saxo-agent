"""Persistence policy for local PDF layout extraction jobs."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


class PdfLayoutJobNotFound(FileNotFoundError):
    """Raised when a job identifier or its persisted state is unavailable."""


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

    def load_state(self, job_id: str) -> dict[str, Any]:
        try:
            return json.loads(
                (self.job_dir(job_id) / "job.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError) as exc:
            raise PdfLayoutJobNotFound(job_id) from exc

    def write_state(self, job_id: str, state: dict[str, Any]) -> None:
        target = self.job_dir(job_id) / "job.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(target)

    @classmethod
    def public_state(cls, state: dict[str, Any]) -> dict[str, Any]:
        return {key: state.get(key) for key in cls._PUBLIC_FIELDS}
