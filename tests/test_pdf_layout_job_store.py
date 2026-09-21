from __future__ import annotations

import pytest

from saxophone.workflows.pdf_layout_jobs import PdfLayoutJobNotFound, PdfLayoutJobStore


def test_job_store_round_trips_state_atomically(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    store.job_dir(job_id).mkdir()
    state = {"id": job_id, "status": "uploaded", "error": None}

    store.write_state(job_id, state)

    assert store.load_state(job_id) == state
    assert not (store.job_dir(job_id) / "job.json.tmp").exists()


@pytest.mark.parametrize("job_id", ["", "../escape", "not-a-uuid"])
def test_job_store_rejects_invalid_job_identifiers(tmp_path, job_id: str) -> None:
    with pytest.raises(PdfLayoutJobNotFound):
        PdfLayoutJobStore(tmp_path).job_dir(job_id)


def test_public_state_exposes_only_browser_safe_fields() -> None:
    state = {"id": "job", "status": "completed", "traceback": "secret", "source": "path"}

    assert PdfLayoutJobStore.public_state(state) == {"id": "job", "status": "completed", "error": None, **{key: None for key in (
        "original_filename", "created_at", "started_at", "finished_at", "device", "language",
        "page_count", "phase", "progress_pages", "progress_total", "progress_images",
    )}}


def test_load_state_rejects_json_payloads_that_are_not_state_objects(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    job_dir = store.job_dir(job_id)
    job_dir.mkdir()
    (job_dir / "job.json").write_text("[\"not-a-state-object\"]", encoding="utf-8")

    with pytest.raises(PdfLayoutJobNotFound):
        store.load_state(job_id)
