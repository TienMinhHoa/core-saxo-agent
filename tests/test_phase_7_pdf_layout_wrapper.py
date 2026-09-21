from __future__ import annotations

from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_pdf_layout_entrypoint_is_only_a_compatibility_wrapper() -> None:
    source = (SOURCE_ROOT / "src" / "pdf_layout_web.py").read_text(encoding="utf-8")

    assert "from saxophone.interfaces.pdf_layout_web import app, main" in source
    assert "FastAPI(" not in source
    assert "@app." not in source
    assert "def _run_extraction" not in source


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


def test_pdf_layout_route_delegates_extraction_orchestration_to_workflow() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "from saxophone.workflows import run_extraction" in source
    assert "def _run_extraction" not in source
    assert "importlib.import_module" not in source
    assert "traceback.format_exc" not in source


def test_pdf_layout_route_uses_the_workflows_public_api() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "from saxophone.workflows import run_extraction" in source
    assert "from saxophone.workflows.pdf_layout_extraction import run_extraction" not in source


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


def test_pdf_layout_interface_delegates_public_state_projection_to_job_store() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "def _public_state" not in source
    assert "JOB_STORE.public_state(state)" in source


def test_pdf_layout_missing_job_maps_store_error_to_http_404(monkeypatch) -> None:
    from fastapi import HTTPException

    from saxophone.interfaces import pdf_layout_web
    from saxophone.workflows.pdf_layout_jobs import PdfLayoutJobNotFound

    class MissingJobStore:
        def load_state(self, job_id: str):
            raise PdfLayoutJobNotFound(job_id)

    monkeypatch.setattr(pdf_layout_web, "JOB_STORE", MissingJobStore())

    try:
        pdf_layout_web._load_state("12345678-1234-5678-1234-567812345678")
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
