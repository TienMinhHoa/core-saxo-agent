from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest


class FakePaddleResult(dict):
    def save_to_json(self, save_path: str | Path) -> None:
        Path(save_path).write_text(
            json.dumps({"res": dict(self)}, ensure_ascii=False), encoding="utf-8"
        )

    def save_to_markdown(self, save_path: str | Path) -> None:
        destination = Path(save_path)
        destination.mkdir(parents=True, exist_ok=True)
        markdown = destination / "document.md"
        previous = markdown.read_text(encoding="utf-8") if markdown.exists() else ""
        markdown.write_text(
            previous + f"## Page {self['page_index'] + 1}\n\n{self['parsing_res_list'][0]['block_content']}\n",
            encoding="utf-8",
        )
        images = destination / "images"
        images.mkdir(exist_ok=True)
        (images / f"page-{self['page_index'] + 1:04d}-01.jpg").write_bytes(b"jpg")


def _result() -> FakePaddleResult:
    return FakePaddleResult(
        input_path="source.pdf",
        page_index=0,
        page_count=1,
        width=1200,
        height=1600,
        model_settings={"use_doc_orientation_classify": False},
        parsing_res_list=[
            {
                "block_label": "text",
                "block_content": "Noi dung co dau",
                "block_bbox": [10, 20, 300, 90],
                "block_id": 7,
                "block_order": 1,
                "group_id": 2,
                "block_polygon_points": [[10, 20], [300, 20], [300, 90], [10, 90]],
            }
        ],
    )


def test_client_constructs_only_a_remote_vllm_paddle_pipeline(tmp_path: Path) -> None:
    from saxophone.extraction.paddle_vllm import PaddleVllmLayoutExtractor

    calls: list[object] = []

    class Pipeline:
        def predict(self, source: str):
            calls.append(("predict", source))
            return [_result()]

    def pipeline_factory(**kwargs):
        calls.append(("factory", kwargs))
        return Pipeline()

    extractor = PaddleVllmLayoutExtractor(
        "http://ocr-host:8000/v1", pipeline_factory=pipeline_factory
    )
    extractor.extract(tmp_path / "source.pdf", tmp_path / "extraction")

    assert calls[0] == (
        "factory",
        {
            "vl_rec_backend": "vllm-server",
            "vl_rec_server_url": "http://ocr-host:8000/v1",
        },
    )
    assert calls[1] == ("predict", str(tmp_path / "source.pdf"))


def test_remote_client_source_has_no_local_gpu_or_legacy_extractor_dependency() -> None:
    source = (
        Path(__file__).parents[1]
        / "src"
        / "saxophone"
        / "extraction"
        / "paddle_vllm.py"
    ).read_text(encoding="utf-8")

    assert "paddle.device" not in source
    assert "cuda" not in source.lower()
    assert "extracted" not in source
    assert "PPStructureV3" not in source

    interface_source = (
        Path(__file__).parents[1]
        / "src"
        / "saxophone"
        / "interfaces"
        / "pdf_layout_web.py"
    ).read_text(encoding="utf-8")
    assert 'id="device"' not in interface_source
    assert "gpu:0" not in interface_source


def test_pdf_layout_jobs_are_always_queued_for_remote_vllm(tmp_path: Path) -> None:
    from saxophone.workflows import PdfLayoutJobStore

    store = PdfLayoutJobStore(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"
    store.create_uploaded_job(
        "source.pdf", job_id=job_id, created_at="2026-09-21T00:00:00Z"
    )

    state = store.queue_extraction(job_id)

    assert state["device"] == "remote-vllm"
    assert state["language"] == "multilingual"


def test_primary_backend_mounts_pdf_layout_routes() -> None:
    factory_source = (
        Path(__file__).parents[1] / "src" / "saxophone" / "app" / "factory.py"
    ).read_text(encoding="utf-8")

    assert 'app.mount("/pdf-layout", pdf_layout_app)' in factory_source


def test_layout_only_application_does_not_require_general_model_service_settings() -> None:
    from fastapi.testclient import TestClient

    from saxophone.main import create_application

    app = create_application({"SAXO_LAYOUT_ONLY": "true"})
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/pdf-layout" in paths
    assert TestClient(app).get("/pdf-layout/").status_code == 200


def test_main_exposes_layout_only_cli_switch() -> None:
    source = (
        Path(__file__).parents[1] / "src" / "saxophone" / "main.py"
    ).read_text(encoding="utf-8")

    assert '"--layout-only"' in source
    assert 'SAXO_LAYOUT_ONLY' in source


def test_client_preserves_paddle_page_and_layout_schema(tmp_path: Path) -> None:
    from saxophone.extraction.paddle_vllm import PaddleVllmLayoutExtractor

    class Pipeline:
        def predict(self, source: str):
            return [_result()]

    report = PaddleVllmLayoutExtractor(
        "http://ocr-host:8000/v1", pipeline_factory=lambda **_: Pipeline()
    ).extract(tmp_path / "source.pdf", tmp_path / "extraction")

    payload = json.loads(
        (tmp_path / "extraction" / "source" / "layout" / "page-0001.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["res"]["page_index"] == 0
    assert payload["res"]["width"] == 1200
    assert payload["res"]["height"] == 1600
    assert payload["res"]["parsing_res_list"] == _result()["parsing_res_list"]
    assert report.page_count == 1


def test_client_preserves_boxes_polygons_markdown_and_image_references(tmp_path: Path) -> None:
    from saxophone.extraction import read_layout_pages
    from saxophone.extraction.paddle_vllm import PaddleVllmLayoutExtractor

    class Pipeline:
        def predict(self, source: str):
            return [_result()]

    output = tmp_path / "extraction"
    report = PaddleVllmLayoutExtractor(
        "http://ocr-host:8000/v1", pipeline_factory=lambda **_: Pipeline()
    ).extract(tmp_path / "source.pdf", output)

    source_output = output / "source"
    raw_block = json.loads(
        (source_output / "layout" / "page-0001.json").read_text(encoding="utf-8")
    )["res"]["parsing_res_list"][0]
    assert raw_block["block_bbox"] == [10, 20, 300, 90]
    assert raw_block["block_polygon_points"] == [
        [10, 20],
        [300, 20],
        [300, 90],
        [10, 90],
    ]
    assert "Noi dung co dau" in (source_output / "document.md").read_text(encoding="utf-8")
    assert (source_output / "images" / "page-0001-01.jpg").is_file()
    assert report.image_count == 1
    assert read_layout_pages(source_output / "layout", lambda page: f"/pages/{page}") == [
        {
            "page": 1,
            "width": 1200.0,
            "height": 1600.0,
            "image_url": "/pages/1",
            "blocks": [
                {
                    "id": 7,
                    "order": 1,
                    "label": "text",
                    "text": "Noi dung co dau",
                    "bbox": [10.0, 20.0, 300.0, 90.0],
                }
            ],
        }
    ]


def test_workflow_marks_remote_failure_without_local_fallback(tmp_path: Path) -> None:
    from saxophone.workflows import PdfLayoutArtifactPaths
    from saxophone.workflows.pdf_layout_extraction import run_extraction

    updates: list[dict[str, object]] = []
    paths = PdfLayoutArtifactPaths(
        source_pdf=tmp_path / "source.pdf",
        extraction=tmp_path / "extraction",
        pages=tmp_path / "pages",
        layout=tmp_path / "extraction" / "source" / "layout",
    )

    class FailedRemoteExtractor:
        def extract(self, source_pdf: Path, output_dir: Path, *, on_progress=None):
            raise ConnectionError("vLLM unavailable")

    def update_state(job_id: str, patch: dict[str, object]) -> dict[str, object]:
        updates.append(patch)
        return {"id": job_id, "language": "vi", **patch}

    run_extraction(
        "job-id",
        artifact_paths=lambda _: paths,
        update_state=update_state,
        render_pages=lambda *_: pytest.fail("must not render after remote failure"),
        extraction_lock=threading.Lock(),
        extractor_factory=lambda: FailedRemoteExtractor(),
    )

    assert updates[-1]["status"] == "failed"
    assert updates[-1]["phase"] == "failed"
    assert updates[-1]["error"] == "ConnectionError: vLLM unavailable"
    assert not paths.extraction.exists()
