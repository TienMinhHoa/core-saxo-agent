"""Reusable pure helpers for the legacy Gradio compatibility surface."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .util import require_within


def display_status(code: str) -> str:
    """Map a stable status code to fixed UI text without model output."""
    messages = {
        "ready": "Ready.",
        "no_match": "No approved document matched this request.",
        "semantic_unavailable": "Semantic retrieval is unavailable.",
        "no_match_best_effort": "No complete match was found; showing the best final candidate.",
        "asset_invalid": "A source asset is invalid and cannot be displayed.",
        "system_error": "The document could not be loaded. Try again later.",
    }
    return messages.get(code, messages["system_error"])


def format_answer_cost(result: dict[str, Any]) -> str:
    """Format answer-model usage and cost for the compatibility UI."""
    usage = result["usage"]
    cost = result["cost"]
    estimated = " (ước lượng)" if not usage.get("available", False) else ""
    return "\n".join([
        "### Chi phí riêng của lượt tổng hợp",
        f"- Model: `{result['model']}` · thinking: enabled · effort: `{result['reasoning_effort']}`",
        (
            f"- Input: **{int(usage['input_tokens']):,}** token{estimated} "
            f"(cache hit {int(usage['cache_hit_tokens']):,}, miss {int(usage['cache_miss_tokens']):,})"
        ),
        (
            f"- Output: **{int(usage['output_tokens']):,}** token{estimated} "
            f"(reasoning {int(usage.get('reasoning_tokens', 0)):,})"
        ),
        f"- Khung giá: `{cost['period']}` (UTC) · ảnh gửi kèm: {result.get('image_inputs', 0)}",
        (
            f"- **Tổng chi phí trả lời: `${cost['total_usd']:.8f}`** "
            f"(input `${cost['input_usd']:.8f}`, output `${cost['output_usd']:.8f}`)"
        ),
        "> Chi phí này chỉ tính request tổng hợp DeepSeek, không tính embedding/retrieval.",
    ])


def _safe_image_path(record: dict[str, Any], image: dict[str, Any]) -> Path | None:
    image_path = image.get("image_path")
    extraction_dir = record.get("extraction_dir")
    if not isinstance(image_path, str) or not isinstance(extraction_dir, str):
        return None
    try:
        path = require_within(Path(extraction_dir), Path(image_path))
    except ValueError:
        return None
    return path if path.is_file() else None


def chroma_asset_paths(chroma_dir: str | Path) -> list[str]:
    """Return existing sidecar-approved image paths for the UI allow-list."""
    sidecar = Path(chroma_dir) / "chunk-records.json"
    if not sidecar.is_file():
        return []
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    paths: set[str] = set()
    for record in payload.values():
        if not isinstance(record, dict):
            continue
        for image in record.get("images", []):
            if isinstance(image, dict):
                path = _safe_image_path(record, image)
                if path is not None:
                    paths.add(str(path))
    return sorted(paths)


def render_source_bundle(
    service: Any,
    response: dict[str, Any],
    access_scope: str,
) -> tuple[str, list[tuple[str, str]]]:
    """Render a validated catalog response for the compatibility UI."""
    article: list[str] = []
    images: list[tuple[str, str]] = []
    for item in response["items"]:
        source = item["source"]
        article.append(
            "<section class='source-item'>"
            f"<h2>{html.escape(str(item['item_type']))}</h2>"
            f"<p class='source-meta'>{html.escape(str(source['title']))}"
            f" · {html.escape(str(source.get('author') or 'Unknown author'))}</p>"
        )
        for block in item["blocks"]:
            if block["kind"] == "asset":
                path = service.asset_path(
                    item["item_id"], item["item_version"], block["block_id"], access_scope
                )
                images.append((str(path), f"Source block {block['block_id']}"))
            else:
                tag = "h3" if block["kind"] == "heading" else "pre"
                article.append(f"<{tag}>{block['text']}</{tag}>")
        article.append("</section>")
    return "\n".join(article), images


def render_chroma_results(hits: list[dict[str, Any]]) -> tuple[str, list[tuple[str, str]]]:
    """Render retrieved chunks and return only verified sidecar images."""
    article: list[str] = []
    images: list[tuple[str, str]] = []
    seen_images: set[str] = set()
    for rank, hit in enumerate(hits, start=1):
        header = html.escape(str(hit.get("header") or "(no header)"))
        page_start = html.escape(str(hit.get("page_start") or "?"))
        page_end = html.escape(str(hit.get("page_end") or "?"))
        score = hit.get("score")
        score_text = f"{float(score):.3f}" if isinstance(score, (int, float)) else "?"
        content = html.escape(str(hit.get("content") or ""), quote=False)
        article.append(
            "<section class='chroma-hit'>"
            f"<h3>{rank}. {header}</h3>"
            f"<p class='source-meta'>Pages {page_start}-{page_end} · score {score_text} · "
            f"{len(hit.get('images') or [])} verified images</p>"
            f"<pre>{content}</pre>"
        )
        for image in hit.get("images", []):
            if not isinstance(image, dict):
                continue
            path = _safe_image_path(hit, image)
            if path is None or str(path) in seen_images:
                continue
            seen_images.add(str(path))
            figure_number = image.get("figure_number") or "figure"
            figure_title = image.get("figure_title")
            caption = image.get("caption") or image.get("summary") or "No caption"
            label = str(figure_number)
            if figure_title:
                label += f" · {figure_title}"
            images.append((str(path), f"{header} · {label}: {caption}"))
        article.append("</section>")
    return "\n".join(article), images


__all__ = [
    "chroma_asset_paths",
    "display_status",
    "format_answer_cost",
    "render_chroma_results",
    "render_source_bundle",
]
