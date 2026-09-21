from __future__ import annotations

from saxophone.extraction import render_pdf_pages


def test_render_pdf_pages_runs_poppler_and_returns_numeric_page_order(monkeypatch, tmp_path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"pdf")
    page_dir = tmp_path / "pages"
    monkeypatch.setattr("saxophone.extraction.pdf_pages.shutil.which", lambda _: "pdftoppm")

    def fake_run(command, **kwargs):
        assert command == ["pdftoppm", "-png", "-r", "144", str(source), str(page_dir / "page")]
        assert kwargs == {"check": True, "capture_output": True, "text": True}
        (page_dir / "page-10.png").write_bytes(b"10")
        (page_dir / "page-2.png").write_bytes(b"2")

    monkeypatch.setattr("saxophone.extraction.pdf_pages.subprocess.run", fake_run)
    assert render_pdf_pages(source, page_dir) == ["page-2.png", "page-10.png"]


def test_render_pdf_pages_fails_with_actionable_message_when_poppler_is_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("saxophone.extraction.pdf_pages.shutil.which", lambda _: None)

    try:
        render_pdf_pages(tmp_path / "source.pdf", tmp_path / "pages")
    except RuntimeError as exc:
        assert "pdftoppm" in str(exc)
    else:
        raise AssertionError("missing Poppler must fail before filesystem work")
