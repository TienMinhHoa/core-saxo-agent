"""ChromaDB indexing for header chunks produced by the Paddle/VLM pipeline.

The vector document is deliberately text-only: image markup and VLM HTML
blocks are removed before calling the embedding provider.  The original chunk
and the validated image references are kept in a JSON sidecar, so retrieval can
return the source text together with image paths without putting image bytes
into the embedding request.

This module is intentionally separate from ``music_rag.semantic``.  The
existing catalog/search flow is unchanged until the Chroma index has been
reviewed.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .embeddings import EmbeddingProvider, OpenAIEmbeddingProvider
from .errors import MusicRagError
from .util import require_within, sha256_bytes, stable_id

HTML_IMAGE = re.compile(r"<img\b[^>]*?\b(?:src|href)\s*=\s*([\"'])(.*?)\1[^>]*>", re.IGNORECASE)
MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
IMAGE_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
DIV_TAG = re.compile(r"</?div\b[^>]*>", re.IGNORECASE)
VLM_BLOCK = re.compile(r"<div\s+class=[\"']vlm-figure-caption[\"'][^>]*>.*?</div>", re.IGNORECASE | re.DOTALL)

DEFAULT_COLLECTION = "music_theory_header_chunks"
DEFAULT_CHROMA_DIR = "runtime/chroma/music-theory-for-dummies"
# OpenAI's embedding endpoint currently accepts at most 8,192 tokens per
# input.  We keep a margin because this indexer intentionally does not depend
# on a downloadable tokenizer (the tokenizer may be unavailable in an
# offline/container run).  The character guard below is deliberately
# conservative and is only used to decide which source chunks to skip.
DEFAULT_MAX_INPUT_TOKENS = 8_000
EMBEDDING_CHARS_PER_TOKEN_GUARD = 2
DEFAULT_EMBEDDING_PRICES = {
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
    "text-embedding-ada-002": 0.10,
}


def _require_chromadb() -> Any:
    try:
        import chromadb
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError("chromadb_not_installed: run `uv sync`") from exc
    return chromadb


def _normalise_asset_ref(value: str) -> str:
    value = html.unescape(value).strip()
    if value.startswith("<") and ">" in value:
        value = value[1 : value.index(">")]
    else:
        value = value.split(None, 1)[0]
    value = value.split("#", 1)[0].split("?", 1)[0].replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def _image_ref(line: str) -> str | None:
    match = HTML_IMAGE.search(line)
    if match:
        return _normalise_asset_ref(match.group(2))
    match = MARKDOWN_IMAGE.search(line)
    return _normalise_asset_ref(match.group(1)) if match else None


def _image_refs(content: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for line in content.splitlines():
        ref = _image_ref(line)
        if ref and ref not in seen:
            refs.append(ref)
            seen.add(ref)
    return refs


def _text_without_images(content: str) -> str:
    """Remove image/VLM presentation markup while retaining nearby text."""
    content = VLM_BLOCK.sub("", content)
    text_lines: list[str] = []
    for line in content.splitlines():
        if _image_ref(line):
            # The extractor emits image-only div lines.  Removing the tags too
            # keeps this robust if a future source line has text beside an
            # image instead of discarding that neighbouring text.
            cleaned = DIV_TAG.sub("", IMAGE_TAG.sub("", line))
            cleaned = MARKDOWN_IMAGE.sub("", cleaned).strip()
            if cleaned:
                text_lines.append(cleaned)
            continue
        text_lines.append(line)
    return re.sub(r"\s+", " ", "\n".join(text_lines)).strip()


def _latest_vlm_results(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.is_file():
        return {}
    latest: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid VLM JSONL at line {line_number}: {exc}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("asset"), str):
            continue
        latest[_normalise_asset_ref(value["asset"])] = value
    return latest


def _valid_vlm(record: dict[str, Any] | None) -> bool:
    if not isinstance(record, dict) or record.get("status") not in {None, "completed"}:
        return False
    analysis = record.get("analysis")
    if analysis == "No valid content":
        return False
    return isinstance(analysis, dict) and analysis.get("result") != "No valid content"


def _image_detail(record: dict[str, Any], ref: str, extraction_dir: Path) -> dict[str, Any]:
    analysis = record.get("analysis") if isinstance(record.get("analysis"), dict) else {}
    try:
        path = require_within(extraction_dir, extraction_dir / ref)
        image_path = str(path) if path.is_file() else None
    except ValueError:
        image_path = None
    return {
        "asset_ref": ref,
        "image_path": image_path,
        "figure_number": analysis.get("figure_number"),
        "figure_title": analysis.get("figure_title"),
        "caption": analysis.get("caption"),
        "summary": analysis.get("summary"),
        "asset_type": analysis.get("asset_type"),
    }


def load_chunk_records(
    chunks_path: str | Path,
    *,
    extraction_dir: str | Path | None = None,
    vlm_results_path: str | Path | None = None,
    start_index: int = 0,
    max_chunks: int | None = None,
) -> list[dict[str, Any]]:
    """Load chunk JSON and build source records with valid-image metadata."""
    chunks_file = Path(chunks_path)
    payload = json.loads(chunks_file.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError("chunks_json_must_be_a_list")
    extraction_root = Path(extraction_dir) if extraction_dir is not None else chunks_file.parent
    extraction_root = extraction_root.resolve()
    vlm_path = Path(vlm_results_path) if vlm_results_path is not None else extraction_root / "vlm-figures" / "figure-vlm-results.jsonl"
    vlm = _latest_vlm_results(vlm_path)
    if start_index < 0:
        raise ValueError("start_index_must_be_nonnegative")
    selected = payload[start_index:] if max_chunks is None else payload[start_index : start_index + max(max_chunks, 0)]
    records: list[dict[str, Any]] = []
    for index, chunk in enumerate(selected, start=start_index):
        if not isinstance(chunk, dict):
            continue
        header = str(chunk.get("header") or "").strip()
        content = str(chunk.get("content") or "").strip()
        search_text = " ".join(part for part in (header, _text_without_images(content)) if part).strip()
        if not search_text:
            continue
        all_refs = _image_refs(content)
        valid_refs = [ref for ref in all_refs if _valid_vlm(vlm.get(ref))]
        image_details = [_image_detail(vlm[ref], ref, extraction_root) for ref in valid_refs]
        page_start = chunk.get("page_start")
        page_end = chunk.get("page_end")
        chunk_id = stable_id(
            "chunk",
            str(chunks_file.resolve()),
            str(index),
            header,
            str(page_start),
            str(page_end),
        )
        # Only the text sent to the embedding API controls reuse.  A VLM
        # relabeling an image must update the sidecar, but should not trigger a
        # second paid embedding request for unchanged text.
        content_hash = sha256_bytes(search_text.encode("utf-8"))
        records.append({
            "chunk_id": chunk_id,
            "chunk_index": index,
            "header": header,
            "content": content,
            "search_text": search_text,
            "page_start": page_start,
            "page_end": page_end,
            "all_image_refs": all_refs,
            "image_refs": valid_refs,
            "images": image_details,
            "content_hash": content_hash,
            "source_chunks": str(chunks_file.resolve()),
            "extraction_dir": str(extraction_root),
        })
    return records


def _collection(client: Any, name: str) -> Any:
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def _existing_hashes(collection: Any) -> tuple[dict[str, str], set[str]]:
    current = collection.get(include=["metadatas"])
    ids = [str(value) for value in current.get("ids", [])]
    metadatas = current.get("metadatas", []) or []
    hashes = {
        chunk_id: str(metadata.get("content_hash"))
        for chunk_id, metadata in zip(ids, metadatas)
        if isinstance(metadata, dict) and metadata.get("content_hash") is not None
    }
    return hashes, set(ids)


def _metadata(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "header": record["header"],
        "page_start": int(record["page_start"]) if isinstance(record["page_start"], int) else -1,
        "page_end": int(record["page_end"]) if isinstance(record["page_end"], int) else -1,
        "image_count": len(record["image_refs"]),
        "all_image_count": len(record["all_image_refs"]),
        "image_refs_json": json.dumps(record["image_refs"], ensure_ascii=False),
        "content_hash": record["content_hash"],
        "source_chunks": record["source_chunks"],
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f"{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _price_per_million(model: str) -> float:
    configured = os.environ.get("MUSIC_RAG_EMBEDDING_PRICE_USD_PER_MILLION")
    if configured:
        return float(configured)
    return DEFAULT_EMBEDDING_PRICES.get(model, 0.0)


def _estimated_input_tokens(text: str) -> int:
    """Return a conservative token estimate for the preflight length guard.

    This is not used for billing (the API usage value is used whenever it is
    available).  Two characters per token errs on the safe side for HTML and
    non-ASCII text, ensuring an oversized source chunk is skipped before it
    can make the whole embedding batch fail with HTTP 400.
    """
    return max(1, math.ceil(len(text) / EMBEDDING_CHARS_PER_TOKEN_GUARD))


def _oversized_chunks(records: list[dict[str, Any]], max_input_tokens: int) -> list[dict[str, Any]]:
    limit = max_input_tokens * EMBEDDING_CHARS_PER_TOKEN_GUARD
    return [
        record
        for record in records
        if len(record["search_text"]) > limit
    ]


def _print_progress(done: int, total: int) -> None:
    percent = 100.0 if total == 0 else done * 100.0 / total
    print(f"[embed] {done}/{total} chunks ({percent:5.1f}%)", flush=True)


def _upsert_embedding_batch(collection: Any, batch: list[dict[str, Any]], vectors: list[list[float]]) -> None:
    if len(vectors) != len(batch):
        raise ValueError("embedding_response_count_mismatch")
    collection.upsert(
        ids=[record["chunk_id"] for record in batch],
        embeddings=vectors,
        documents=[record["search_text"] for record in batch],
        metadatas=[_metadata(record) for record in batch],
    )


def _embed_pending(
    collection: Any,
    pending: list[dict[str, Any]],
    provider: EmbeddingProvider,
    *,
    batch_size: int,
    workers: int,
    progress: bool,
) -> None:
    """Embed pending batches concurrently; Chroma writes stay in the caller thread."""
    batches = [pending[offset : offset + batch_size] for offset in range(0, len(pending), batch_size)]
    if progress:
        print(f"[embed] {len(pending)} chunks in {len(batches)} batch(es), workers={workers}", flush=True)
        _print_progress(0, len(pending))
    if not batches:
        return

    completed = 0
    if workers == 1:
        for batch in batches:
            vectors = provider.embed([record["search_text"] for record in batch])
            _upsert_embedding_batch(collection, batch, vectors)
            completed += len(batch)
            if progress:
                _print_progress(completed, len(pending))
        return

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="embedding") as executor:
        futures = {
            executor.submit(provider.embed, [record["search_text"] for record in batch]): batch
            for batch in batches
        }
        for future in as_completed(futures):
            batch = futures[future]
            vectors = future.result()
            _upsert_embedding_batch(collection, batch, vectors)
            completed += len(batch)
            if progress:
                _print_progress(completed, len(pending))


def build_chroma_index(
    chunks_path: str | Path,
    *,
    persist_dir: str | Path = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_COLLECTION,
    extraction_dir: str | Path | None = None,
    vlm_results_path: str | Path | None = None,
    provider: EmbeddingProvider | None = None,
    batch_size: int = 32,
    start_index: int = 0,
    max_chunks: int | None = None,
    workers: int = 4,
    progress: bool = True,
    max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
    reset: bool = False,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Embed chunk text and persist vectors plus source/image sidecar."""
    if batch_size < 1:
        raise ValueError("batch_size_must_be_positive")
    if workers < 1:
        raise ValueError("workers_must_be_positive")
    if max_input_tokens < 1 or max_input_tokens > 8192:
        raise ValueError("max_input_tokens_must_be_between_1_and_8192")
    records = load_chunk_records(
        chunks_path,
        extraction_dir=extraction_dir,
        vlm_results_path=vlm_results_path,
        start_index=start_index,
        max_chunks=max_chunks,
    )
    chromadb = _require_chromadb()
    destination = Path(persist_dir)
    destination.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(destination))
    if reset:
        existing_collections = {
            str(getattr(item, "name", item)) for item in client.list_collections()
        }
        if collection_name in existing_collections:
            client.delete_collection(name=collection_name)
    collection = _collection(client, collection_name)
    old_hashes, old_ids = _existing_hashes(collection)
    current_ids = {record["chunk_id"] for record in records}
    partial_input = max_chunks is not None or start_index != 0
    # A bounded smoke test must not delete the rest of an already-built index.
    # Full runs reconcile stale chunks against the complete input JSON.
    stale_ids = sorted(old_ids - current_ids) if not partial_input else []
    if stale_ids:
        collection.delete(ids=stale_ids)
    oversized = _oversized_chunks(records, max_input_tokens)
    oversized_ids = {record["chunk_id"] for record in oversized}
    # If a previously indexed chunk has since grown beyond the guard, remove
    # its stale vector rather than leaving an outdated result searchable.
    oversized_existing = sorted(oversized_ids & old_ids)
    if oversized_existing:
        collection.delete(ids=oversized_existing)
    pending = [
        record
        for record in records
        if record["chunk_id"] not in oversized_ids
        and old_hashes.get(record["chunk_id"]) != record["content_hash"]
    ]
    embedding_provider = provider or OpenAIEmbeddingProvider()
    if progress:
        reused = len(records) - len(pending)
        reused -= len(oversized)
        print(
            f"[embed] indexed={reused}, pending={len(pending)}, "
            f"skipped_oversized={len(oversized)}, total={len(records)}",
            flush=True,
        )
        for record in oversized:
            print(
                f"[embed] skip oversized chunk_index={record['chunk_index']} "
                f"header={record['header']!r} pages={record['page_start']}-{record['page_end']} "
                f"chars={len(record['search_text'])} "
                f"estimated_tokens={_estimated_input_tokens(record['search_text'])}",
                flush=True,
            )
    if progress and not pending:
        print(
            f"[embed] no new or changed chunks; reused {len(records) - len(oversized)} existing",
            flush=True,
        )
    _embed_pending(
        collection,
        pending,
        embedding_provider,
        batch_size=batch_size,
        workers=workers,
        progress=progress,
    )
    sidecar_path = destination / "chunk-records.json"
    sidecar_records: dict[str, Any] = {}
    if partial_input and not reset and sidecar_path.is_file():
        try:
            existing_sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            if isinstance(existing_sidecar, dict):
                sidecar_records.update(existing_sidecar)
        except (OSError, json.JSONDecodeError):
            sidecar_records = {}
    sidecar_records.update({record["chunk_id"]: record for record in records})
    if stale_ids:
        for chunk_id in stale_ids:
            sidecar_records.pop(chunk_id, None)
    _write_json(sidecar_path, sidecar_records)
    usage = getattr(embedding_provider, "total_usage", {}) or {}
    input_tokens = int(usage.get("prompt_tokens", 0) or 0)
    if input_tokens <= 0:
        # OpenAI returns prompt_tokens for embeddings; this is only a fallback
        # for custom providers that do not expose usage.
        input_tokens = sum(max(1, math.ceil(len(record["search_text"]) / 4)) for record in pending)
        usage_estimated = True
    else:
        usage_estimated = False
    price = _price_per_million(embedding_provider.model)
    report = {
        "chunks_total": len(records),
        "embedded_this_run": len(pending),
        "reused_existing": len(records) - len(pending) - len(oversized),
        "skipped_oversized": len(oversized),
        "max_input_tokens_guard": max_input_tokens,
        "skipped_oversized_chunks": [
            {
                "chunk_id": record["chunk_id"],
                "chunk_index": record["chunk_index"],
                "header": record["header"],
                "page_start": record["page_start"],
                "page_end": record["page_end"],
                "characters": len(record["search_text"]),
                "estimated_tokens": _estimated_input_tokens(record["search_text"]),
            }
            for record in oversized
        ],
        "removed_stale": len(stale_ids),
        "partial_input": partial_input,
        "batch_size": batch_size,
        "workers": workers,
        "model": embedding_provider.model,
        "input_tokens": input_tokens,
        "input_tokens_estimated": usage_estimated,
        "requests": int(usage.get("requests", math.ceil(len(pending) / batch_size)) or 0),
        "price_usd_per_million_input_tokens": price,
        "estimated_cost_usd": input_tokens * price / 1_000_000,
        "persist_dir": str(destination.resolve()),
        "collection": collection_name,
        "sidecar": str(sidecar_path.resolve()),
    }
    destination_report = Path(report_path) if report_path is not None else destination / "index-report.json"
    _write_json(destination_report, report)
    return report


def search_chroma_chunks(
    query: str,
    *,
    persist_dir: str | Path = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_COLLECTION,
    provider: EmbeddingProvider | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search Chroma and return complete chunks with valid image metadata.

    This helper is not wired into ``MusicMaterialService`` yet; the existing
    search flow remains unchanged while the new index is being evaluated.
    """
    if limit < 1:
        return []
    chromadb = _require_chromadb()
    destination = Path(persist_dir)
    client = chromadb.PersistentClient(path=str(destination))
    collection = _collection(client, collection_name)
    available = collection.count()
    if available <= 0:
        return []
    embedding_provider = provider or OpenAIEmbeddingProvider()
    vector = embedding_provider.embed([query])[0]
    result = collection.query(query_embeddings=[vector], n_results=min(limit, available), include=["distances"])
    sidecar_path = destination / "chunk-records.json"
    records = json.loads(sidecar_path.read_text(encoding="utf-8")) if sidecar_path.is_file() else {}
    ids = (result.get("ids") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    hits: list[dict[str, Any]] = []
    for chunk_id, distance in zip(ids, distances):
        record = records.get(chunk_id)
        if not isinstance(record, dict):
            continue
        hits.append({**record, "score": 1.0 - float(distance)})
    return hits


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chunks_json", type=Path, help="Output of extracted.extract_header_chunks")
    parser.add_argument("--persist-dir", type=Path, default=Path(os.environ.get("MUSIC_RAG_CHROMA_DIR", DEFAULT_CHROMA_DIR)))
    parser.add_argument("--collection", default=os.environ.get("MUSIC_RAG_CHROMA_COLLECTION", DEFAULT_COLLECTION))
    parser.add_argument("--extraction-dir", type=Path, help="Directory containing images/ and vlm-figures/")
    parser.add_argument("--vlm-results", type=Path, help="Default: <extraction-dir>/vlm-figures/figure-vlm-results.jsonl")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=int(os.environ.get("MUSIC_RAG_EMBEDDING_WORKERS", "4")), help="Concurrent embedding requests (default: 4)")
    parser.add_argument(
        "--max-input-tokens",
        type=int,
        default=int(os.environ.get("MUSIC_RAG_EMBEDDING_MAX_INPUT_TOKENS", str(DEFAULT_MAX_INPUT_TOKENS))),
        help="Conservative per-chunk token guard; oversized chunks are skipped (default: 8000)",
    )
    parser.add_argument("--start-index", type=int, default=0, help="Start at this zero-based chunk index")
    parser.add_argument("--max-chunks", type=int, help="Embed at most N chunks (useful for a cost smoke test)")
    parser.add_argument("--reset", action="store_true", help="Replace the selected Chroma collection")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress output")
    parser.add_argument("--report-output", type=Path, help="Default: <persist-dir>/index-report.json")
    return parser


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    parser = _build_cli()
    args = parser.parse_args()
    if not args.chunks_json.is_file():
        parser.error(f"Chunks JSON not found: {args.chunks_json}")
    if args.max_chunks is not None and args.max_chunks < 1:
        parser.error("--max-chunks must be positive")
    if args.start_index < 0:
        parser.error("--start-index must be nonnegative")
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    if args.workers < 1:
        parser.error("--workers must be positive")
    if args.max_input_tokens < 1 or args.max_input_tokens > 8192:
        parser.error("--max-input-tokens must be between 1 and 8192")
    try:
        report = build_chroma_index(
            args.chunks_json,
            persist_dir=args.persist_dir,
            collection_name=args.collection,
            extraction_dir=args.extraction_dir,
            vlm_results_path=args.vlm_results,
            batch_size=args.batch_size,
            workers=args.workers,
            progress=not args.no_progress,
            max_input_tokens=args.max_input_tokens,
            start_index=args.start_index,
            max_chunks=args.max_chunks,
            reset=args.reset,
            report_path=args.report_output,
        )
    except (OSError, RuntimeError, ValueError, MusicRagError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
