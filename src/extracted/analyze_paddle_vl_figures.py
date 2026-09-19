#!/usr/bin/env python3
"""Enrich every PaddleOCR-VL figure with DeepSeek Flash Vision.

The input is an existing ``paddle_vl_pdf_to_md`` extraction plus its
``image-caption-map.json``. Both heuristic-matched and unmatched figures are
sent to the VLM. Heuristic captions and nearby OCR text are evidence only.

Create a review plan without an API call:
    uv run python -m extracted.analyze_paddle_vl_figures output/input-vl --plan-only
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import html
import json
import mimetypes
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash-vision-exp"
PRICE_USD_PER_MILLION = {
    "input_cache_hit": {"peak": 0.014, "off_peak": 0.007},
    "input_cache_miss": {"peak": 0.44, "off_peak": 0.22},
    "output": {"peak": 1.32, "off_peak": 0.66},
}
IMAGE_LABELS = {"image", "chart", "header_image", "footer_image"}
HTML_TAG = re.compile(r"<[^>]+>")
ASSET_NAME = re.compile(r"^page-(\d{4})-\d+\.(?:jpg|jpeg|png|webp|gif)$", re.IGNORECASE)

SYSTEM_PROMPT = """You extract figures from scanned documents. Be faithful to
the supplied image and OCR evidence. Do not invent text, a figure number, or a
caption. If the submitted asset is not instructional content, return exactly
{"result":"No valid content"}. Return one valid JSON object only, with no
Markdown fence."""

TASK_PROMPT = """Analyze the figure image and its OCR evidence.

Return exactly this JSON shape:
{
  "figure_number": "string or null",
  "figure_title": "string or null",
  "caption": "string or null",
  "caption_source": "visible_in_image|heuristic_match|nearby_context|not_found",
  "asset_type": "figure|chart|table|decorative|logo|unknown",
  "content_transcription": "all legible labels, symbols, and text in reading order; null if none",
  "summary": "concise factual description of the figure; null if unreadable",
  "figure_count": 0,
  "subfigures": [{"index": 1, "label": "string or null", "description": "string", "bbox_normalized": [0, 0, 1, 1]}],
  "uncertainties": ["string"]
}

Rules:
- If this asset is a cover, publisher logo, promotional banner, mascot, icon,
  ornamental graphic, page furniture, or otherwise does not teach/illustrate a
  subject-matter concept, return exactly {"result":"No valid content"}. Do
  not transcribe, summarize, classify, or add any other field in that case.
- Read caption text from the image before trusting heuristic/context evidence.
- Set caption_source to visible_in_image only when you can read it in the image.
- Use heuristic_match only when its caption directly names this image; use
  nearby_context only for a clearly linked reference.
- Figure numbers have the form e.g. "2-2" without the word "Figure".
- figure_count counts distinct diagrams/panels in this submitted image, not
  decorative icons elsewhere on the PDF page.
- For a logo, icon, or decorative asset, use asset_type=decorative or logo,
  figure_count=0, and an empty subfigures array.
- Preserve music notation and mathematical symbols verbatim when legible;
  otherwise describe them rather than guessing.
"""


@dataclass(frozen=True)
class FigureCandidate:
    id: str
    page: int
    asset: Path
    source_asset: str | None
    image_label: str | None
    image_bbox: list[float] | None
    heuristic_caption: str | None
    heuristic_confidence: str | None
    heuristic_score: float | None


def _plain_text(value: str) -> str:
    return " ".join(html.unescape(HTML_TAG.sub(" ", value)).replace("\n", " ").split())


def _raw_page(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("res")
    return nested if isinstance(nested, dict) else payload


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def load_candidates(extraction_dir: Path, caption_map_path: Path) -> list[FigureCandidate]:
    """Read every asset recorded by the caption mapper, including unmatched images."""
    report = _read_json(caption_map_path)
    candidates: dict[str, FigureCandidate] = {}
    for match in report.get("matches", []):
        if not isinstance(match, dict) or not isinstance(match.get("asset"), str):
            continue
        asset = extraction_dir / match["asset"]
        if not asset.is_file():
            continue
        page = int(match["page"])
        identifier = f"page-{page:04d}:{match['asset']}"
        candidates[identifier] = FigureCandidate(
            id=identifier, page=page, asset=asset, source_asset=match.get("source_asset"),
            image_label=match.get("image_label"), image_bbox=match.get("image_bbox"),
            heuristic_caption=match.get("caption"), heuristic_confidence=match.get("confidence"),
            heuristic_score=match.get("score"),
        )
    for item in report.get("unmatched", []):
        if not isinstance(item, dict) or item.get("kind") != "image" or not isinstance(item.get("asset"), str):
            continue
        asset = extraction_dir / item["asset"]
        if not asset.is_file():
            continue
        page = int(item["page"])
        identifier = f"page-{page:04d}:{item['asset']}"
        candidates.setdefault(identifier, FigureCandidate(
            id=identifier, page=page, asset=asset, source_asset=None, image_label=None,
            image_bbox=item.get("bbox"), heuristic_caption=None, heuristic_confidence=None,
            heuristic_score=None,
        ))
    # Some Markdown assets are emitted without a matching layout image/chart
    # block. They still need VLM review, despite lacking bbox/caption evidence.
    image_dir = extraction_dir / "images"
    if image_dir.is_dir():
        for asset in image_dir.iterdir():
            if not asset.is_file():
                continue
            name_match = ASSET_NAME.fullmatch(asset.name)
            if not name_match:
                continue
            page = int(name_match.group(1))
            relative_asset = str(asset.relative_to(extraction_dir))
            identifier = f"page-{page:04d}:{relative_asset}"
            candidates.setdefault(identifier, FigureCandidate(
                id=identifier, page=page, asset=asset, source_asset=None,
                image_label=None, image_bbox=None, heuristic_caption=None,
                heuristic_confidence=None, heuristic_score=None,
            ))
    if not candidates:
        raise ValueError(f"No figure assets found via {caption_map_path}")
    return sorted(candidates.values(), key=lambda item: (item.page, item.asset.name))


def _bbox_distance(first: list[float], second: list[float]) -> float:
    first_left, first_top, first_right, first_bottom = first
    second_left, second_top, second_right, second_bottom = second
    horizontal = max(first_left - second_right, second_left - first_right, 0.0)
    vertical = max(first_top - second_bottom, second_top - first_bottom, 0.0)
    return (horizontal * horizontal + vertical * vertical) ** 0.5


def _page_text(layout_dir: Path, page: int, *, near_bbox: list[float] | None = None, limit: int | None = None, max_distance: float | None = None) -> list[str]:
    path = layout_dir / f"page-{page:04d}.json"
    if not path.is_file():
        return []
    blocks = _raw_page(_read_json(path)).get("parsing_res_list", [])
    if not isinstance(blocks, list):
        return []
    text_blocks: list[tuple[float, int, str]] = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict) or block.get("block_label") in IMAGE_LABELS:
            continue
        text = _plain_text(str(block.get("block_content") or ""))
        if not text:
            continue
        bbox = block.get("block_bbox")
        if near_bbox and isinstance(bbox, list) and len(bbox) == 4:
            try:
                distance = _bbox_distance([float(value) for value in near_bbox], [float(value) for value in bbox])
            except (TypeError, ValueError):
                distance = float("inf")
        else:
            distance = float(index)
        text_blocks.append((distance, index, text))
    text_blocks.sort()
    if max_distance is not None and near_bbox is not None:
        text_blocks = [item for item in text_blocks if item[0] <= max_distance]
    values = [text for _, _, text in text_blocks]
    return values[:limit] if limit is not None else values


def contextual_evidence(extraction_dir: Path, candidate: FigureCandidate) -> dict[str, Any]:
    """Keep same-page context plus adjacent page edges for cross-page captions."""
    layout_dir = extraction_dir / "layout"
    return {
        "heuristic_match": {"caption": candidate.heuristic_caption, "confidence": candidate.heuristic_confidence, "score": candidate.heuristic_score},
        "previous_page_tail": _page_text(layout_dir, candidate.page - 1)[-4:],
        # Spatially nearest text is more useful than page-order text: a page
        # can contain Figure 2-2 and Figure 2-3, whose captions must not be
        # swapped simply because both appear in a broad context window.
        "same_page_nearby_text": _page_text(
            layout_dir, candidate.page, near_bbox=candidate.image_bbox, limit=8, max_distance=250
        ),
        "next_page_head": _page_text(layout_dir, candidate.page + 1)[:4],
    }


def request_text(candidate: FigureCandidate, evidence: dict[str, Any]) -> str:
    return (
        f"{TASK_PROMPT}\n\nCandidate metadata (not visual proof):\n"
        f"- page: {candidate.page}\n- asset: {candidate.asset.name}\n"
        f"- detector label: {candidate.image_label}\n- detector bbox: {candidate.image_bbox}\n\n"
        f"OCR/heuristic evidence:\n{json.dumps(evidence, ensure_ascii=False, indent=2)}"
    )


def _image_data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _usage_value(usage: Any, *names: str) -> int | None:
    """Read a usage field from an SDK model or a plain response dictionary."""
    for name in names:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        if isinstance(value, int):
            return value
    return None


def _usage_dict(response: Any) -> dict[str, Any]:
    """Normalize DeepSeek Chat Completions usage for logging and billing."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {
            "available": False,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cache_hit_tokens": 0,
            "cache_miss_tokens": 0,
            "reasoning_tokens": 0,
        }
    input_tokens = _usage_value(usage, "prompt_tokens", "input_tokens") or 0
    output_tokens = _usage_value(usage, "completion_tokens", "output_tokens") or 0
    total_tokens = _usage_value(usage, "total_tokens")
    cache_hit = _usage_value(usage, "prompt_cache_hit_tokens", "cached_tokens")
    cache_miss = _usage_value(usage, "prompt_cache_miss_tokens")
    # Chat Completions normally exposes both cache fields. If an intermediary
    # only exposes prompt_tokens, conservatively treat the prompt as a miss.
    cache_hit = cache_hit or 0
    cache_miss = input_tokens - cache_hit if cache_miss is None else cache_miss
    reasoning = _usage_value(usage, "reasoning_tokens") or 0
    return {
        "available": True,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens if total_tokens is not None else input_tokens + output_tokens,
        "cache_hit_tokens": cache_hit,
        "cache_miss_tokens": max(cache_miss, 0),
        "reasoning_tokens": reasoning,
    }


def _is_peak(when: datetime) -> bool:
    """DeepSeek peak windows: 01–04 and 06–10 UTC on weekdays."""
    if when.weekday() >= 5:
        return False
    minutes = when.hour * 60 + when.minute
    return 60 <= minutes < 240 or 360 <= minutes < 600


def _cost_dict(usage: dict[str, Any], when: datetime) -> dict[str, Any]:
    period = "peak" if _is_peak(when) else "off_peak"
    hit = usage.get("cache_hit_tokens", 0)
    miss = usage.get("cache_miss_tokens", 0)
    output = usage.get("output_tokens", 0)
    input_hit_cost = hit / 1_000_000 * PRICE_USD_PER_MILLION["input_cache_hit"][period]
    input_miss_cost = miss / 1_000_000 * PRICE_USD_PER_MILLION["input_cache_miss"][period]
    output_cost = output / 1_000_000 * PRICE_USD_PER_MILLION["output"][period]
    return {
        "period": period,
        "utc_timestamp": when.isoformat(),
        "input_cache_hit_usd": round(input_hit_cost, 8),
        "input_cache_miss_usd": round(input_miss_cost, 8),
        "input_usd": round(input_hit_cost + input_miss_cost, 8),
        "output_usd": round(output_cost, 8),
        "total_usd": round(input_hit_cost + input_miss_cost + output_cost, 8),
        "rates_usd_per_million": {
            "input_cache_hit": PRICE_USD_PER_MILLION["input_cache_hit"][period],
            "input_cache_miss": PRICE_USD_PER_MILLION["input_cache_miss"][period],
            "output": PRICE_USD_PER_MILLION["output"][period],
        },
    }


def _append_log(path: Path, event: str, **fields: Any) -> None:
    """Append a normal human-readable event to the run log."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    if event == "run_start":
        line = (
            f"{timestamp} | RUN START | model={fields['model']} | "
            f"candidates={fields['candidates_total']} | pending={fields['pending']} | "
            f"workers={fields['workers']} | retries={fields['retries']}"
        )
    elif event == "request_completed":
        line = (
            f"{timestamp} | completed | {fields['id']} | "
            f"{fields['completed']}/{fields['pending']}"
        )
    elif event == "request_failed":
        line = f"{timestamp} | FAILED | {fields['id']} | {fields['error']}"
    elif event == "run_summary":
        usage = fields["usage_totals"]
        cost = fields["cost_totals"]
        line = (
            f"{timestamp} | RUN SUMMARY\n"
            f"  Completed: {fields['completed']}\n"
            f"  Failed: {fields['failed']}\n"
            f"  Input tokens: {usage['input_tokens']:,}\n"
            f"  Output tokens: {usage['output_tokens']:,}\n"
            f"  Total tokens: {usage['total_tokens']:,}\n"
            f"  Cache hit tokens: {usage['cache_hit_tokens']:,}\n"
            f"  Cache miss tokens: {usage['cache_miss_tokens']:,}\n"
            f"  Input cost: ${cost['input_usd']:.6f}\n"
            f"  Output cost: ${cost['output_usd']:.6f}\n"
            f"  TOTAL COST: ${cost['total_usd']:.6f}\n"
            f"  Elapsed: {fields['elapsed_seconds']:.2f}s\n"
            f"  Results: {fields['results_file']}"
        )
    else:
        line = f"{timestamp} | {event} | {fields}"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def _extract_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("VLM response is not a JSON object")
    return payload


def analyze_one(
    client: Any,
    model: str,
    candidate: FigureCandidate,
    evidence: dict[str, Any],
    *,
    include_usage: bool = False,
) -> dict[str, Any] | tuple[dict[str, Any], dict[str, Any]]:
    """Submit one local figure crop to DeepSeek's OpenAI-compatible API."""
    response = client.chat.completions.create(
        model=model, temperature=0, response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": request_text(candidate, evidence)},
                {"type": "image_url", "image_url": {"url": _image_data_url(candidate.asset)}},
            ]},
        ],
    )
    content = response.choices[0].message.content
    if not isinstance(content, str):
        raise ValueError("DeepSeek response did not contain text content")
    analysis = _extract_json(content)
    if include_usage:
        return analysis, _usage_dict(response)
    return analysis


def _analyze_with_retries(
    client_factory: Any,
    model: str,
    candidate: FigureCandidate,
    evidence: dict[str, Any],
    retries: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Retry transient API/network failures before recording a failed asset."""
    for attempt in range(retries + 1):
        try:
            result = analyze_one(client_factory(), model, candidate, evidence, include_usage=True)
            if not isinstance(result, tuple):
                raise TypeError("Internal error: usage was not returned")
            return result
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def _completed_ids(results_path: Path) -> set[str]:
    if not results_path.is_file():
        return set()
    completed: set[str] = set()
    for line in results_path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("status") == "completed" and isinstance(item.get("id"), str):
            completed.add(item["id"])
    return completed


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_plan(extraction_dir: Path, candidates: Iterable[FigureCandidate], destination: Path, model: str) -> None:
    plan = [{
        "id": item.id, "page": item.page, "asset": str(item.asset.relative_to(extraction_dir)),
        "source_asset": item.source_asset, "image_label": item.image_label,
        "image_bbox": item.image_bbox, "evidence": contextual_evidence(extraction_dir, item),
    } for item in candidates]
    destination.write_text(json.dumps({"engine": "DeepSeek Flash Vision figure enrichment", "model": model, "candidates": plan}, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    # Load this before argparse so environment-backed CLI defaults honour .env.
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extraction_dir", type=Path)
    parser.add_argument("--caption-map", type=Path, help="Default: <extraction-dir>/image-caption-map.json")
    parser.add_argument("--output-dir", type=Path, help="Default: <extraction-dir>/vlm-figures")
    parser.add_argument("--plan-only", action="store_true", help="Write requests/evidence without calling DeepSeek")
    parser.add_argument("--max-figures", type=int, help="Only process the first N pending figures")
    parser.add_argument("--force", action="store_true", help="Analyze completed figures again")
    parser.add_argument(
        "--workers", type=int, default=int(os.getenv("FIGURE_VLM_WORKERS", "4")),
        help="Concurrent DeepSeek requests (default: FIGURE_VLM_WORKERS or 4)",
    )
    parser.add_argument("--retries", type=int, default=2, help="Retries after a failed request (default: 2)")
    parser.add_argument(
        "--log-file", type=Path,
        help="Run log path (default: <output-dir>/figure-vlm-run.log)",
    )
    parser.add_argument("--model", default=os.getenv("FIGURE_VLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--base-url", default=os.getenv("FIGURE_VLM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    args = parser.parse_args()
    if args.max_figures is not None and args.max_figures < 1:
        parser.error("--max-figures must be at least 1")
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    if args.retries < 0:
        parser.error("--retries must be non-negative")

    caption_map = args.caption_map or args.extraction_dir / "image-caption-map.json"
    output_dir = args.output_dir or args.extraction_dir / "vlm-figures"
    try:
        candidates = load_candidates(args.extraction_dir, caption_map)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.plan_only:
        destination = output_dir / "figure-vlm-plan.json"
        write_plan(args.extraction_dir, candidates, destination, args.model)
        print(f"Wrote VLM plan for {len(candidates)} figure(s): {destination}")
        return

    api_key = os.getenv(args.api_key_env)
    if not api_key:
        parser.error(f"Missing {args.api_key_env}. Put it in .env or export it; use --plan-only to inspect requests first.")
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - dependency-specific
        parser.error("The openai package is required for DeepSeek's compatible API.")
        raise AssertionError from exc

    results_path = output_dir / "figure-vlm-results.jsonl"
    completed = set() if args.force else _completed_ids(results_path)
    pending = [item for item in candidates if item.id not in completed]
    if args.max_figures is not None:
        pending = pending[:args.max_figures]
    log_path = args.log_file or output_dir / "figure-vlm-run.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    run_started_at = datetime.now(timezone.utc)
    run_id = run_started_at.strftime("%Y%m%dT%H%M%SZ")
    _append_log(
        log_path,
        "run_start",
        run_id=run_id,
        model=args.model,
        base_url=args.base_url,
        candidates_total=len(candidates),
        pending=len(pending),
        workers=args.workers,
        retries=args.retries,
        results_file=str(results_path),
        pricing=PRICE_USD_PER_MILLION,
    )
    # A synchronous OpenAI client owns an HTTP pool. Keep one client per worker
    # instead of sharing it across threads, and let only the main thread append
    # JSONL so completed records cannot interleave.
    local = threading.local()

    def client_factory() -> Any:
        client = getattr(local, "client", None)
        if client is None:
            client = OpenAI(api_key=api_key, base_url=args.base_url)
            local.client = client
        return client

    print(
        f"[DeepSeek] model={args.model}; pending={len(pending)}; workers={args.workers}; "
        f"output={results_path}",
        flush=True,
    )
    completed_count = 0
    succeeded_count = 0
    failed_count = 0
    usage_totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cache_hit_tokens": 0,
        "cache_miss_tokens": 0,
        "reasoning_tokens": 0,
    }
    cost_totals = {
        "input_cache_hit_usd": 0.0,
        "input_cache_miss_usd": 0.0,
        "input_usd": 0.0,
        "output_usd": 0.0,
        "total_usd": 0.0,
    }
    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="deepseek-vlm") as executor:
        futures = {}
        for candidate in pending:
            evidence = contextual_evidence(args.extraction_dir, candidate)
            futures[executor.submit(
                _analyze_with_retries,
                client_factory,
                args.model,
                candidate,
                evidence,
                args.retries,
            )] = (candidate, evidence, time.monotonic(), datetime.now(timezone.utc))
        for future in as_completed(futures):
            candidate, evidence, started, request_started_at = futures[future]
            completed_count += 1
            try:
                analysis, usage = future.result()
                cost = _cost_dict(usage, request_started_at)
                payload: dict[str, Any] = {
                    "id": candidate.id, "status": "completed", "page": candidate.page,
                    "asset": str(candidate.asset.relative_to(args.extraction_dir)),
                    "source_asset": candidate.source_asset, "image_bbox": candidate.image_bbox,
                    "evidence": evidence, "model": args.model, "analysis": analysis,
                    "usage": usage, "cost": cost,
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                }
                succeeded_count += 1
                for key in usage_totals:
                    usage_totals[key] += usage.get(key, 0)
                for key in cost_totals:
                    cost_totals[key] += cost.get(key, 0.0)
                _append_log(
                    log_path,
                    "request_completed",
                    run_id=run_id,
                    id=candidate.id,
                    page=candidate.page,
                    asset=str(candidate.asset.relative_to(args.extraction_dir)),
                    completed=completed_count,
                    pending=len(pending),
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    total_tokens=usage["total_tokens"],
                    cache_hit_tokens=usage["cache_hit_tokens"],
                    cache_miss_tokens=usage["cache_miss_tokens"],
                    usage_available=usage["available"],
                    cost_usd=cost["total_usd"],
                    cost=cost,
                    elapsed_seconds=payload["elapsed_seconds"],
                )
                print(f"[DeepSeek] {completed_count}/{len(pending)} completed {candidate.id}", flush=True)
            except Exception as exc:  # retain progress and continue to the next figure
                failed_count += 1
                payload = {
                    "id": candidate.id, "status": "failed", "page": candidate.page,
                    "asset": str(candidate.asset.relative_to(args.extraction_dir)), "error": repr(exc),
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                }
                _append_log(
                    log_path,
                    "request_failed",
                    run_id=run_id,
                    id=candidate.id,
                    page=candidate.page,
                    asset=str(candidate.asset.relative_to(args.extraction_dir)),
                    error=repr(exc),
                    elapsed_seconds=payload["elapsed_seconds"],
                )
                print(f"[DeepSeek] {completed_count}/{len(pending)} failed {candidate.id}: {exc}", flush=True)
            _append_jsonl(results_path, payload)
    _append_log(
        log_path,
        "run_summary",
        run_id=run_id,
        candidates_total=len(candidates),
        pending=len(pending),
        completed=succeeded_count,
        failed=failed_count,
        usage_totals=usage_totals,
        cost_totals={key: round(value, 8) for key, value in cost_totals.items()},
        elapsed_seconds=round((datetime.now(timezone.utc) - run_started_at).total_seconds(), 2),
        results_file=str(results_path),
    )
    print(
        f"[DeepSeek] summary completed={succeeded_count} failed={failed_count} "
        f"input_tokens={usage_totals['input_tokens']} output_tokens={usage_totals['output_tokens']} "
        f"cost_usd={cost_totals['total_usd']:.6f} log={log_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
