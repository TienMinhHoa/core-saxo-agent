"""PaddleOCR-VL client adapter backed only by a remote vLLM server."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse


class PaddleResult(Protocol):
    """Small result surface used from PaddleOCR-VL."""

    def get(self, key: str, default: Any = None) -> Any: ...

    def save_to_json(self, save_path: str | Path) -> None: ...

    def save_to_markdown(self, save_path: str | Path) -> None: ...


class PaddlePipeline(Protocol):
    def predict(self, source: str) -> Iterable[PaddleResult]: ...


PipelineFactory = Callable[..., PaddlePipeline]
ProgressCallback = Callable[[int, int | None, int], None]


@dataclass(frozen=True, slots=True)
class PaddleVllmExtractionReport:
    page_count: int
    image_count: int


class PaddleVllmLayoutExtractor:
    """Persist Paddle page results while inference runs on remote vLLM."""

    def __init__(
        self,
        server_url: str,
        *,
        pipeline_factory: PipelineFactory | None = None,
    ) -> None:
        self._server_url = _validate_server_url(server_url)
        self._pipeline_factory = pipeline_factory or _load_pipeline

    def extract(
        self,
        source_pdf: Path,
        output_dir: Path,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> PaddleVllmExtractionReport:
        pipeline = self._pipeline_factory(
            vl_rec_backend="vllm-server",
            vl_rec_server_url=self._server_url,
        )
        source_output = output_dir / source_pdf.stem
        layout_dir = source_output / "layout"
        page_count = 0

        for sequence, result in enumerate(pipeline.predict(str(source_pdf))):
            if not hasattr(result, "save_to_json") or not hasattr(result, "save_to_markdown"):
                raise TypeError("PaddleOCR-VL returned an unsupported result object")
            page_index = _page_index(result, sequence)
            layout_dir.mkdir(parents=True, exist_ok=True)
            result.save_to_json(save_path=layout_dir / f"page-{page_index + 1:04d}.json")
            result.save_to_markdown(save_path=source_output)
            page_count += 1
            if on_progress is not None:
                on_progress(page_count, _page_total(result), _count_images(source_output))

        if page_count == 0:
            raise ValueError("PaddleOCR-VL returned no pages")
        return PaddleVllmExtractionReport(
            page_count=page_count,
            image_count=_count_images(source_output),
        )


def paddle_vllm_extractor_from_environment() -> PaddleVllmLayoutExtractor:
    """Build the adapter at job runtime so imports do not require OCR extras."""
    value = os.environ.get("SAXO_PADDLE_VLLM_SERVER_URL", "")
    if not value.strip():
        raise RuntimeError("SAXO_PADDLE_VLLM_SERVER_URL is required for PDF layout extraction")
    return PaddleVllmLayoutExtractor(value)


def _load_pipeline(**kwargs: Any) -> PaddlePipeline:
    try:
        from paddleocr import PaddleOCRVL
    except ImportError as exc:
        raise RuntimeError(
            "PaddleOCR client is not installed; run 'uv sync --extra paddle-client'"
        ) from exc
    return PaddleOCRVL(**kwargs)


def _validate_server_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Paddle vLLM server URL must be an absolute HTTP(S) URL")
    return normalized


def _page_index(result: PaddleResult, fallback: int) -> int:
    value = result.get("page_index", fallback)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else fallback


def _page_total(result: PaddleResult) -> int | None:
    value = result.get("page_count")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _count_images(output_dir: Path) -> int:
    images = output_dir / "images"
    if not images.is_dir():
        return 0
    return sum(1 for path in images.rglob("*") if path.is_file())
