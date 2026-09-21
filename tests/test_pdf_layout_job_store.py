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


def test_create_uploaded_job_owns_initial_state_and_directory(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"

    state = store.create_uploaded_job(
        job_id,
        original_filename="source.pdf",
        created_at="2026-09-21T00:00:00Z",
    )

    assert state == {
        "id": job_id,
        "original_filename": "source.pdf",
        "status": "uploaded",
        "created_at": "2026-09-21T00:00:00Z",
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
    assert store.load_state(job_id) == state
    assert store.job_dir(job_id).is_dir()


def test_create_uploaded_job_rejects_existing_job_directory(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    store.job_dir(job_id).mkdir()

    with pytest.raises(FileExistsError):
        store.create_uploaded_job(job_id, "source.pdf", "2026-09-21T00:00:00Z")


def test_queue_extraction_owns_transition_and_persists_requested_options(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    store.create_uploaded_job(job_id, "source.pdf", "2026-09-21T00:00:00Z")

    state = store.queue_extraction(job_id, device="cpu", language="vi")

    assert state["status"] == "queued"
    assert state["device"] == "cpu"
    assert state["language"] == "vi"
    assert state["phase"] == "queued"
    assert state["progress_pages"] == 0
    assert state["progress_total"] is None
    assert state["progress_images"] == 0
    assert state["error"] is None
    assert store.load_state(job_id) == state


def test_queue_extraction_rejects_non_restartable_status(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    state = store.create_uploaded_job(job_id, "source.pdf", "2026-09-21T00:00:00Z")
    state["status"] = "running"
    store.write_state(job_id, state)

    with pytest.raises(ValueError, match="cannot be queued"):
        store.queue_extraction(job_id, device="cpu", language="vi")


def test_job_store_owns_pdf_artifact_paths(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    job_dir = store.job_dir(job_id)

    assert store.source_pdf_path(job_id) == job_dir / "source.pdf"
    assert store.extraction_dir(job_id) == job_dir / "extraction"
    assert store.pages_dir(job_id) == job_dir / "pages"
    assert store.layout_dir(job_id) == job_dir / "extraction" / "source" / "layout"
