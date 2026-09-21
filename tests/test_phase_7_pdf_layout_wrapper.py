from __future__ import annotations

from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_pdf_layout_entrypoint_is_only_a_compatibility_wrapper() -> None:
    source = (SOURCE_ROOT / "src" / "pdf_layout_web.py").read_text(encoding="utf-8")

    assert "from saxophone.interfaces.pdf_layout_web import app, main" in source
    assert "FastAPI(" not in source
    assert "@app." not in source
    assert "def _run_extraction" not in source
