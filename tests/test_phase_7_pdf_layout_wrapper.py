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

    assert "from saxophone.extraction import finite_number" in source
    assert "def _number" not in source
    assert "    return _number(" not in source


def test_pdf_layout_route_delegates_extraction_orchestration_to_workflow() -> None:
    source = (
        SOURCE_ROOT / "src" / "saxophone" / "interfaces" / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")

    assert "from saxophone.workflows.pdf_layout_extraction import run_extraction" in source
    assert "def _run_extraction" not in source
    assert "importlib.import_module" not in source
    assert "traceback.format_exc" not in source
