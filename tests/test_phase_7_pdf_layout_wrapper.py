from __future__ import annotations

from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def test_pdf_layout_docstrings_use_primary_backend_entrypoint() -> None:
    interface_source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "uv run saxophone-api" in interface_source
    assert "uv run pdf-layout-web" not in interface_source


def test_pdf_layout_route_uses_extraction_number_policy_directly() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    extraction_layout = (
        SOURCE_ROOT / "src" / "saxophone" / "extraction" / "layout_view.py"
    ).read_text(encoding="utf-8")

    assert "from .layout import finite_number" in extraction_layout
    assert "def _number" not in source
    assert "    return _number(" not in source


def test_pdf_layout_interface_does_not_keep_dead_job_directory_helper() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "def _job_dir" not in source
    assert "JOB_STORE.job_dir(" not in source


def test_pdf_layout_route_delegates_extraction_orchestration_to_workflow() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "from saxophone.workflows import start_extraction" in source
    assert "def _run_extraction" not in source
    assert "importlib.import_module" not in source
    assert "traceback.format_exc" not in source


def test_pdf_layout_route_uses_the_workflows_public_api() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "from saxophone.workflows import start_extraction" in source
    assert "from saxophone.workflows.pdf_layout_extraction import run_extraction" not in source


def test_pdf_layout_interface_uses_the_workflows_public_job_store_facade() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "PdfLayoutJobNotFound" in source
    assert "PdfLayoutJobStore" in source
    assert "from saxophone.workflows.pdf_layout_jobs import" not in source


def test_pdf_layout_artifact_paths_are_exported_by_the_workflows_facade() -> None:
    from saxophone import workflows

    assert "PdfLayoutArtifactPaths" in workflows.__all__
    assert workflows.__all__.count("PdfLayoutArtifactPaths") == 1


def test_pdf_extraction_workflow_uses_public_artifact_paths_facade() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "workflows" / "pdf_layout_extraction.py"
    ).read_text(encoding="utf-8")

    assert "from saxophone.workflows import PdfLayoutArtifactPaths" in source
    assert "from saxophone.workflows.pdf_layout_jobs import" not in source


def test_pdf_extraction_workflow_is_declared_in_public_workflows_exports() -> None:
    from saxophone import workflows

    assert "run_extraction" in workflows.__all__
    assert workflows.__all__.count("run_extraction") == 1


def test_pdf_layout_interface_delegates_layout_reading_to_extraction_policy() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "from saxophone.extraction import read_layout_pages" in source
    assert "def _layout_pages" not in source
    assert "def _normalise_blocks" not in source


def test_pdf_layout_interface_delegates_completed_layout_response_to_workflow() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "from saxophone.workflows import" in source
    assert "load_layout_pages(" in source
    assert '"pages": read_layout_pages(' not in source


def test_layout_workflow_composes_state_and_pages_through_injected_policies() -> None:
    from pathlib import Path

    from saxophone.workflows import load_layout_pages

    calls: list[object] = []

    def load_completed(job_id: str) -> dict[str, object]:
        calls.append(("state", job_id))
        return {"id": job_id, "status": "completed", "private": "hidden"}

    def public_state(state: dict[str, object]) -> dict[str, object]:
        calls.append(("public", state))
        return {"id": state["id"], "status": state["status"]}

    def read_pages(path: Path, page_url) -> list[dict[str, object]]:
        calls.append(("pages", path, page_url(2)))
        return [{"page": 2}]

    result = load_layout_pages(
        "job-id",
        load_completed_state=load_completed,
        public_state=public_state,
        layout_path=lambda job_id: Path("layout") / job_id,
        read_pages=read_pages,
        page_url=lambda page: f"/pages/{page}",
    )

    assert result == {"job": {"id": "job-id", "status": "completed"}, "pages": [{"page": 2}]}
    assert calls == [
        ("state", "job-id"),
        ("public", {"id": "job-id", "status": "completed", "private": "hidden"}),
        ("pages", Path("layout") / "job-id", "/pages/2"),
    ]


def test_pdf_layout_interface_does_not_keep_local_pdf_raster_implementation() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "def _render_pages" not in source
    assert "def _page_number" not in source
    assert "subprocess.run" not in source
    assert "shutil.which(\"pdftoppm\")" not in source
    assert "render_pages=render_pdf_pages" in source


def test_pdf_layout_interface_delegates_extraction_launch_to_workflow() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "from saxophone.workflows import start_extraction" in source
    assert "threading.Thread" not in source
    assert ".start()" not in source


def test_extraction_workflow_exposes_thread_launch_policy() -> None:
    from saxophone import workflows

    assert "start_extraction" in workflows.__all__
    assert workflows.__all__.count("start_extraction") == 1


def test_start_extraction_configures_and_starts_daemon_worker() -> None:
    from saxophone.workflows import start_extraction

    calls: list[object] = []

    class Worker:
        def start(self) -> None:
            calls.append("started")

    def factory(**kwargs):
        calls.append(kwargs)
        return Worker()

    artifact_paths = lambda job_id: job_id
    update_state = lambda job_id, updates: updates
    render_pages = lambda source, destination: []
    extraction_lock = object()

    start_extraction(
        "job-id",
        artifact_paths=artifact_paths,
        update_state=update_state,
        render_pages=render_pages,
        extraction_lock=extraction_lock,
        thread_factory=factory,
    )

    assert calls[1] == "started"
    worker_kwargs = calls[0]
    assert worker_kwargs["args"] == ("job-id",)
    assert worker_kwargs["daemon"] is True
    assert worker_kwargs["kwargs"] == {
        "artifact_paths": artifact_paths,
        "update_state": update_state,
        "render_pages": render_pages,
        "extraction_lock": extraction_lock,
    }


def test_pdf_layout_interface_delegates_public_state_projection_to_job_store() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "def _public_state" not in source
    assert "JOB_STORE.public_state(state)" in source


def test_pdf_layout_interface_delegates_layout_readiness_to_job_store() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "load_completed_state=JOB_STORE.load_completed_state" in source
    assert 'state.get("status") != "completed"' not in source


def test_pdf_upload_route_delegates_initial_state_creation_to_job_store() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")
    create_job_source = source.split("@app.post(\"/api/jobs/{job_id}/extract\")", 1)[0]

    assert "JOB_STORE.create_uploaded_job(" in create_job_source
    assert "job_dir.mkdir(" not in create_job_source
    assert '"progress_pages": 0' not in create_job_source
    assert '"original_filename": supplied_name' not in create_job_source


def test_pdf_upload_interface_does_not_own_job_identity_or_timestamp() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "import uuid" not in source
    assert "import time" not in source
    assert "uuid.uuid4" not in source
    assert "_timestamp" not in source
    assert "JOB_STORE.create_uploaded_job(\n        supplied_name\n    )" in source


def test_pdf_upload_cleanup_is_owned_by_job_store() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")
    create_job_source = source.split("@app.post(\"/api/jobs/{job_id}/extract\")", 1)[0]

    assert "JOB_STORE.discard_job(job_id)" in create_job_source
    assert "shutil.rmtree(job_dir" not in create_job_source


def test_pdf_upload_interface_does_not_keep_dead_upload_writer() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")
    create_job_source = source.split('@app.post("/api/jobs/{job_id}/extract")', 1)[0]

    assert "async def _save_upload" not in source
    assert "await upload.read(" not in create_job_source
    assert "JOB_STORE.save_uploaded_pdf" in create_job_source


def test_pdf_extract_route_delegates_queue_transition_to_job_store() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")
    extract_source = source.split('@app.post("/api/jobs/{job_id}/extract")', 1)[1]
    extract_source = extract_source.split('@app.get("/api/jobs/{job_id}")', 1)[0]

    assert "JOB_STORE.queue_extraction(" in extract_source
    assert "state.update(" not in extract_source
    assert 'state.get("status")' not in extract_source


def test_pdf_extract_route_maps_store_queue_conflict_to_http_409(monkeypatch) -> None:
    from fastapi import HTTPException

    from saxophone.interfaces import pdf_layout_web

    class ConflictingJobStore:
        def queue_extraction(self, job_id: str):
            raise ValueError("job cannot be queued from its current status")

    monkeypatch.setattr(pdf_layout_web, "JOB_STORE", ConflictingJobStore())

    try:
        pdf_layout_web.start_extraction("job-id")
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("store queue conflicts must map to HTTP 409")


def test_pdf_extract_route_launches_workflow_without_self_recursion(monkeypatch) -> None:
    from saxophone.interfaces import pdf_layout_web

    expected_job_id = "12345678-1234-5678-1234-567812345678"
    state = {"id": expected_job_id, "status": "queued"}
    calls: list[object] = []

    class FakeJobStore:
        def queue_extraction(self, job_id: str):
            calls.append(("queue", job_id))
            return state

        def public_state(self, current_state):
            calls.append(("public", current_state))
            return {"id": current_state["id"], "status": current_state["status"]}

        def artifact_paths(self, job_id: str):
            return f"paths:{job_id}"

        def update_state(self, job_id: str, updates):
            return updates

    def fake_launcher(job_id: str, **kwargs) -> None:
        calls.append(("launch", job_id, kwargs))

    monkeypatch.setattr(pdf_layout_web, "JOB_STORE", FakeJobStore())
    monkeypatch.setattr(pdf_layout_web, "launch_extraction", fake_launcher)

    result = pdf_layout_web.start_extraction(expected_job_id)

    assert result == {"id": expected_job_id, "status": "queued"}
    assert calls[0] == ("queue", expected_job_id)
    assert calls[1][0] == "launch"
    assert calls[1][1] == expected_job_id
    assert calls[1][2]["artifact_paths"].__self__ is pdf_layout_web.JOB_STORE
    assert calls[1][2]["artifact_paths"](expected_job_id) == f"paths:{expected_job_id}"
    assert calls[2] == ("public", state)


def test_pdf_extract_route_does_not_own_option_validation_policy() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")
    extract_source = source.split('@app.post("/api/jobs/{job_id}/extract")', 1)[1]
    extract_source = extract_source.split('@app.get("/api/jobs/{job_id}")', 1)[0]

    assert "re.fullmatch" not in extract_source
    assert "device.strip()" not in extract_source
    assert "language.strip()" not in extract_source


def test_pdf_layout_routes_delegate_artifact_paths_to_job_store() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert ' / "source.pdf"' not in source
    assert ' / "pages"' not in source
    assert ' / "extraction" / "source" / "layout"' not in source
    assert "JOB_STORE.artifact_paths(" in source
    assert "JOB_STORE.save_uploaded_pdf" in source
    assert "JOB_STORE.page_image_path(job_id, page_number)" in source
    assert "artifact_paths(current_job_id).layout" in source


def test_pdf_page_route_delegates_rendered_page_path_policy_to_job_store() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "JOB_STORE.page_image_path(job_id, page_number)" in source
    assert 'f"page-{page_number}.png"' not in source


def test_pdf_page_route_maps_missing_job_to_http_404(monkeypatch) -> None:
    from fastapi import HTTPException

    from saxophone.interfaces import pdf_layout_web
    from saxophone.workflows.pdf_layout_jobs import PdfLayoutJobNotFound

    class MissingJobStore:
        def page_image_path(self, job_id: str, page_number: int):
            raise PdfLayoutJobNotFound(job_id)

    monkeypatch.setattr(pdf_layout_web, "JOB_STORE", MissingJobStore())

    try:
        pdf_layout_web.page_image(
            "12345678-1234-5678-1234-567812345678", 1
        )
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("missing PDF jobs must map to HTTP 404")


def test_pdf_job_store_keeps_one_public_artifact_path_policy() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "workflows" / "pdf_layout_jobs.py"
    ).read_text(encoding="utf-8")

    for helper in ("source_pdf_path", "pages_dir", "layout_dir", "extraction_dir"):
        assert f"def {helper}(" not in source
    assert "def artifact_paths(" in source


def test_pdf_extraction_workflow_accepts_typed_artifact_path_policy() -> None:
    workflow_source = (
        SOURCE_ROOT / "src" / "saxophone" / "workflows" / "pdf_layout_extraction.py"
    ).read_text(encoding="utf-8")
    interface_source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "job_dir:" not in workflow_source
    assert "artifact_paths:" in workflow_source
    assert "artifact_paths=JOB_STORE.artifact_paths" in interface_source


def test_pdf_extraction_workflow_consumes_one_artifact_path_policy() -> None:
    workflow_source = (
        SOURCE_ROOT / "src" / "saxophone" / "workflows" / "pdf_layout_extraction.py"
    ).read_text(encoding="utf-8")
    interface_source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "artifact_paths:" in workflow_source
    assert "source_pdf_path:" not in workflow_source
    assert "extraction_dir:" not in workflow_source
    assert "pages_dir:" not in workflow_source
    assert "artifact_paths=JOB_STORE.artifact_paths" in interface_source


def test_pdf_extraction_workflow_delegates_state_patches_to_job_store() -> None:
    workflow_source = (
        SOURCE_ROOT / "src" / "saxophone" / "workflows" / "pdf_layout_extraction.py"
    ).read_text(encoding="utf-8")
    interface_source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "update_state:" in workflow_source
    assert "load_state:" not in workflow_source
    assert "write_state:" not in workflow_source
    assert "update_state=JOB_STORE.update_state" in interface_source
    assert "def _write_state" not in interface_source


def test_layout_route_uses_job_store_projection_at_runtime(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    from saxophone.interfaces import pdf_layout_web

    expected_job_id = "12345678-1234-5678-1234-567812345678"
    state = {"id": expected_job_id, "status": "completed", "secret": "hidden"}

    class FakeJobStore:
        def load_completed_state(self, job_id: str):
            assert job_id == expected_job_id
            return state

        def artifact_paths(self, job_id: str):
            assert job_id == expected_job_id
            return SimpleNamespace(layout=tmp_path)

        def public_state(self, loaded_state):
            return {"id": loaded_state["id"], "status": loaded_state["status"]}

    monkeypatch.setattr(pdf_layout_web, "JOB_STORE", FakeJobStore())
    monkeypatch.setattr(
        pdf_layout_web,
        "read_layout_pages",
        lambda layout_dir, page_url: [{"page": 1, "image_url": page_url(1)}],
    )

    result = pdf_layout_web.job_layout(expected_job_id)

    assert result == {
        "job": {"id": expected_job_id, "status": "completed"},
        "pages": [
            {
                "page": 1,
                "image_url": f"/pdf-layout/api/jobs/{expected_job_id}/pages/1",
            }
        ],
    }


def test_pdf_layout_missing_job_maps_store_error_to_http_404(monkeypatch) -> None:
    from fastapi import HTTPException

    from saxophone.interfaces import pdf_layout_web
    from saxophone.workflows.pdf_layout_jobs import PdfLayoutJobNotFound

    class MissingJobStore:
        def load_completed_state(self, job_id: str):
            raise PdfLayoutJobNotFound(job_id)

    monkeypatch.setattr(pdf_layout_web, "JOB_STORE", MissingJobStore())

    try:
        pdf_layout_web.job_layout("12345678-1234-5678-1234-567812345678")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("missing PDF jobs must map to HTTP 404")


def test_layout_reader_keeps_page_url_and_skips_invalid_layout_payloads(tmp_path) -> None:
    import json

    from saxophone.extraction import read_layout_pages

    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()
    (layout_dir / "page-001.json").write_text(
        json.dumps(
            {
                "page_index": 0,
                "width": 100,
                "height": 200,
                "coordinate_space": {
                    "name": "raw_pdf_raster_pixels",
                    "transform_to_source": "identity",
                },
                "parsing_res_list": [],
            }
        ),
        encoding="utf-8",
    )
    (layout_dir / "page-002.json").write_text(
        json.dumps({"width": "nan", "height": 200, "coordinate_space": "pdf_raster"}),
        encoding="utf-8",
    )

    pages = read_layout_pages(layout_dir, lambda page: f"/pages/{page}")

    assert pages == [
        {
            "page": 1,
            "width": 100.0,
            "height": 200.0,
            "image_url": "/pages/1",
            "blocks": [],
        }
    ]
