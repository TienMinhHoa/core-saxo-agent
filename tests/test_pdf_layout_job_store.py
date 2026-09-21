from __future__ import annotations

from io import BytesIO
from uuid import UUID

import pytest

from saxophone.workflows.pdf_layout_jobs import (
    PdfLayoutArtifactPaths,
    PdfLayoutJobRequestError,
    PdfLayoutJobNotFound,
    PdfLayoutJobStore,
)


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


def test_load_public_state_loads_and_projects_state_at_store_boundary(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    store.job_dir(job_id).mkdir()
    store.write_state(job_id, {"id": job_id, "status": "uploaded", "private": "hidden"})

    projected = store.load_public_state(job_id)

    assert projected["id"] == job_id
    assert projected["status"] == "uploaded"
    assert "private" not in projected
    assert set(projected) == set(PdfLayoutJobStore._PUBLIC_FIELDS)


def test_create_uploaded_job_owns_initial_state_and_directory(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"

    state = store.create_uploaded_job(
        original_filename="source.pdf",
        job_id=job_id,
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


def test_create_uploaded_job_generates_identity_and_timestamp_when_omitted(tmp_path) -> None:
    state = PdfLayoutJobStore(tmp_path).create_uploaded_job("source.pdf")

    UUID(state["id"])
    assert state["created_at"].endswith("Z")


def test_create_uploaded_job_rejects_existing_job_directory(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    store.job_dir(job_id).mkdir()

    with pytest.raises(FileExistsError):
        store.create_uploaded_job("source.pdf", job_id=job_id, created_at="2026-09-21T00:00:00Z")


def test_job_store_owns_discarding_a_failed_upload(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    store.create_uploaded_job("source.pdf", job_id=job_id, created_at="2026-09-21T00:00:00Z")
    store.artifact_paths(job_id).source_pdf.write_bytes(b"partial upload")

    store.discard_job(job_id)

    assert not store.job_dir(job_id).exists()


def test_queue_extraction_owns_transition_and_persists_requested_options(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    store.create_uploaded_job("source.pdf", job_id=job_id, created_at="2026-09-21T00:00:00Z")

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


@pytest.mark.parametrize("device", ["", "cuda", "gpu:", "gpu:x", "GPU: "])
def test_queue_extraction_rejects_invalid_device_at_store_boundary(tmp_path, device: str) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    store.create_uploaded_job("source.pdf", job_id=job_id, created_at="2026-09-21T00:00:00Z")

    with pytest.raises(PdfLayoutJobRequestError, match="device"):
        store.queue_extraction(job_id, device=device, language="vi")


@pytest.mark.parametrize("language", ["", "v", "vi-VN", "vi-日本語", "日本語"])
def test_queue_extraction_rejects_invalid_language_at_store_boundary(tmp_path, language: str) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    store.create_uploaded_job("source.pdf", job_id=job_id, created_at="2026-09-21T00:00:00Z")

    with pytest.raises(PdfLayoutJobRequestError, match="language"):
        store.queue_extraction(job_id, device="cpu", language=language)


def test_queue_extraction_normalizes_options_before_persisting(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    store.create_uploaded_job("source.pdf", job_id=job_id, created_at="2026-09-21T00:00:00Z")

    state = store.queue_extraction(job_id, device=" GPU:0 ", language=" EN ")

    assert state["device"] == "gpu:0"
    assert state["language"] == "en"


def test_queue_extraction_rejects_non_restartable_status(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    state = store.create_uploaded_job("source.pdf", job_id=job_id, created_at="2026-09-21T00:00:00Z")
    state["status"] = "running"
    store.write_state(job_id, state)

    with pytest.raises(ValueError, match="cannot be queued"):
        store.queue_extraction(job_id, device="cpu", language="vi")


def test_update_state_owns_atomic_workflow_state_patch(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    store.create_uploaded_job("source.pdf", job_id=job_id, created_at="2026-09-21T00:00:00Z")

    state = store.update_state(job_id, {"status": "running", "phase": "extracting"})

    assert state["status"] == "running"
    assert state["phase"] == "extracting"
    assert store.load_state(job_id) == state
    assert not (store.job_dir(job_id) / "job.json.tmp").exists()


def test_job_store_exposes_one_typed_artifact_path_policy(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    job_dir = store.job_dir(job_id)

    paths = store.artifact_paths(job_id)

    assert isinstance(paths, PdfLayoutArtifactPaths)
    assert paths.source_pdf == job_dir / "source.pdf"
    assert paths.extraction == job_dir / "extraction"
    assert paths.pages == job_dir / "pages"
    assert paths.layout == job_dir / "extraction" / "source" / "layout"


def test_job_store_persists_uploaded_pdf_and_returns_byte_count(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    store.create_uploaded_job("source.pdf", job_id=job_id, created_at="2026-09-21T00:00:00Z")

    written = store.save_uploaded_pdf(job_id, BytesIO(b"pdf bytes"), max_bytes=32)

    assert written == 9
    assert store.artifact_paths(job_id).source_pdf.read_bytes() == b"pdf bytes"


def test_job_store_owns_validated_rendered_page_path(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"

    assert store.page_image_path(job_id, 3) == tmp_path / job_id / "pages" / "page-3.png"


@pytest.mark.parametrize("page_number", [0, -1, True, 1.5, "1"])
def test_job_store_rejects_invalid_rendered_page_numbers(tmp_path, page_number) -> None:
    store = PdfLayoutJobStore(tmp_path)

    with pytest.raises(ValueError, match="page_number"):
        store.page_image_path("12345678-1234-5678-1234-567812345678", page_number)


def test_job_store_rejects_upload_over_limit_without_leaving_partial_file(tmp_path) -> None:
    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    store.create_uploaded_job("source.pdf", job_id=job_id, created_at="2026-09-21T00:00:00Z")

    with pytest.raises(ValueError, match="upload exceeds maximum"):
        store.save_uploaded_pdf(job_id, BytesIO(b"12345"), max_bytes=4)

    assert not store.artifact_paths(job_id).source_pdf.exists()
