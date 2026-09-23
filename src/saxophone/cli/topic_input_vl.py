"""Estimate and run the direct-provider topic flow for extracted VL chunks."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import tiktoken

from saxophone.ingestion import IngestionCommand, IngestionSourceChunk
from saxophone.ingestion.use_cases import build_chunk_tagging_requests
from saxophone.main import create_application
from saxophone.retrieval.question_retrieval import QuestionRequest
from saxophone.services.extract_topic import TopicIngestionRequest
from saxophone.tagging import ParagraphBlock, parse_chunk_paragraphs
from saxophone.tagging.structured_chunk import _chunk_prompt

_EMBEDDING_TOKEN_LIMIT = 8000
_EMBEDDING_SPLIT_TARGET = 7600


@dataclass(frozen=True, slots=True)
class PreparedInputVlSource:
    source_hash: str
    source_version: str
    chunks: tuple[IngestionSourceChunk, ...]
    paragraphs: tuple[ParagraphBlock, ...]


class _TopicFacade(Protocol):
    async def ingest_document(self, request: TopicIngestionRequest) -> Any: ...

    async def answer_question(self, request: QuestionRequest) -> Any: ...


def build_input_vl_source(
    source_path: Path,
    *,
    document_ref: str,
    access_scope: str,
    caption_map_path: Path | None = None,
    limit: int | None = None,
) -> PreparedInputVlSource:
    """Load normalized header chunks without re-tagging report metadata."""

    rows = _chunk_rows(source_path)
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        rows = rows[:limit]
    if not rows:
        raise ValueError("source must contain at least one chunk")
    canonical = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    source_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    rows = _split_oversized_rows(rows)
    captions = _caption_metadata(caption_map_path)
    chunks = tuple(
        _source_chunk(
            row,
            index=index,
            document_ref=document_ref,
            source_version=source_hash,
            access_scope=access_scope,
        )
        for index, row in enumerate(rows)
    )
    paragraphs = tuple(
        paragraph
        for chunk in chunks
        for paragraph in parse_chunk_paragraphs(chunk, image_metadata=captions)
    )
    return PreparedInputVlSource(source_hash, source_hash, chunks, paragraphs)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    prepared = build_input_vl_source(
        args.source,
        document_ref=args.document_ref,
        access_scope=args.access_scope,
        caption_map_path=args.caption_map,
        limit=args.limit,
    )
    estimate = _estimate(prepared)
    print(json.dumps(estimate, ensure_ascii=False, indent=2))
    if not args.execute:
        print("Estimate only. Add --execute to start billable provider calls.")
        return
    asyncio.run(
        _run(
            prepared,
            question=None if args.ingest_only else args.question,
        )
    )


async def _run(prepared: PreparedInputVlSource, *, question: str | None) -> None:
    app = create_application()
    async with app.router.lifespan_context(app):
        container = app.state.container
        if container.settings.model_provider != "direct":
            raise RuntimeError(
                "Set SAXO_MODEL_PROVIDER=direct before executing this command"
            )
        facade = container.extract_topic
        if facade is None:
            raise RuntimeError(
                "Topic flow is disabled; set SAXO_CHUNK_TAGGING_ENABLED=true"
            )
        await _execute_ingestion(
            prepared,
            facade=facade,
            model_profile=container.settings.litellm_model_profile,
            question=question,
        )


async def _execute_ingestion(
    prepared: PreparedInputVlSource,
    *,
    facade: _TopicFacade,
    model_profile: str,
    question: str | None,
) -> None:
    """Run tagging, embedding, and indexing, with optional answer generation."""

    command = IngestionCommand(
        document_ref=prepared.chunks[0].document_ref,
        source_version=prepared.source_version,
        chunking_profile="header-json-v1",
        tagging_profile="topic-v1",
        embedding_profile=model_profile,
        index_profile="topic-index-v1",
        access_scope=prepared.chunks[0].access_scope,
    )
    report = await facade.ingest_document(
        TopicIngestionRequest(
            command=command,
            chunks=prepared.chunks,
            paragraphs=prepared.paragraphs,
            resolution_profile="topic-v1",
            ingestion_run_id=f"{command.document_ref}-{prepared.source_hash[:12]}",
            source_hash=prepared.source_hash,
        )
    )
    print(json.dumps({"ingestion": asdict(report)}, ensure_ascii=False, indent=2))
    if not report.indexed:
        if report.errors:
            raise RuntimeError(f"Ingestion is not ready: {report.errors}")
        print(
            json.dumps(
                {
                    "incomplete": {
                        "indexed": False,
                        "answer_generated": False,
                        "warnings": report.warnings,
                    }
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if question is None:
        print(
            json.dumps(
                {
                    "completed": {
                        "mode": "ingest-only",
                        "answer_generated": False,
                    }
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    answer = await facade.answer_question(QuestionRequest(question))
    print(json.dumps({"answer": asdict(answer)}, ensure_ascii=False, indent=2))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Estimate or run topic tagging for output_v3/input-vl",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("output_v3/input-vl/document-header-chunks.json"),
    )
    parser.add_argument(
        "--caption-map",
        type=Path,
        default=Path("output_v3/input-vl/image-caption-map.json"),
    )
    parser.add_argument("--document-ref", default="music-theory-for-dummies")
    parser.add_argument("--access-scope", default="default")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--question",
        default="What is a major triad?",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Start billable DeepSeek and OpenAI API calls",
    )
    parser.add_argument(
        "--ingest-only",
        action="store_true",
        help="Run tagging, embedding, and indexing without retrieval or answering",
    )
    return parser


def _chunk_rows(source_path: Path) -> list[dict[str, object]]:
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read chunk source: {source_path}") from error
    if not isinstance(payload, list):
        raise ValueError("chunk source must be a JSON list")
    rows: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, Mapping):
            raise ValueError("chunk source items must be mappings")
        header = _text(item.get("header"), "header")
        content = _text(item.get("content"), "content")
        page_start = _optional_page(item.get("page_start"), "page_start")
        page_end = _optional_page(item.get("page_end"), "page_end")
        rows.append(
            {
                "header": header,
                "content": content,
                "page_start": page_start,
                "page_end": page_end,
            }
        )
    return rows


def _source_chunk(
    row: Mapping[str, object],
    *,
    index: int,
    document_ref: str,
    source_version: str,
    access_scope: str,
) -> IngestionSourceChunk:
    header = _text(row.get("header"), "header")
    content = _text(row.get("content"), "content")
    part_index = row.get("part_index")
    part_count = row.get("part_count")
    display_header = (
        f"{header} (Part {part_index} of {part_count})"
        if isinstance(part_index, int) and isinstance(part_count, int)
        else header
    )
    digest = hashlib.sha256(f"{header}\n{content}".encode("utf-8")).hexdigest()[:16]
    metadata: dict[str, object] = {
        "heading": display_header,
        "heading_level": 2,
        "page_start": row.get("page_start"),
        "page_end": row.get("page_end"),
    }
    if isinstance(part_index, int) and isinstance(part_count, int):
        metadata.update(
            {
                "source_heading": header,
                "part_index": part_index,
                "part_count": part_count,
            }
        )
    return IngestionSourceChunk(
        chunk_id=f"{document_ref}:{source_version}:{index}:{digest}",
        document_ref=document_ref,
        source_version=source_version,
        search_text=f"## {display_header}\n\n{content}",
        access_scope=access_scope,
        metadata=metadata,
    )


def _caption_metadata(path: Path | None) -> dict[str, dict[str, object]]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read caption map: {path}") from error
    if not isinstance(payload, Mapping):
        raise ValueError("caption map must be a mapping")
    matches = payload.get("matches", [])
    if not isinstance(matches, list):
        raise ValueError("caption map matches must be a list")
    result: dict[str, dict[str, object]] = {}
    for item in matches:
        if not isinstance(item, Mapping):
            continue
        asset = item.get("asset")
        caption = item.get("caption")
        if (
            isinstance(asset, str)
            and asset.strip()
            and isinstance(caption, str)
            and caption.strip()
        ):
            result[asset.strip()] = {"caption": caption.strip()}
    return result


def _estimate(prepared: PreparedInputVlSource) -> dict[str, object]:
    requests = build_chunk_tagging_requests(prepared.chunks, prepared.paragraphs)
    prompt_characters = sum(len(_chunk_prompt(request)) for request in requests)
    approximate_input_tokens = math.ceil(prompt_characters / 3.5)
    return {
        "document_ref": prepared.chunks[0].document_ref,
        "source_version": prepared.source_version,
        "chunks": len(prepared.chunks),
        "paragraphs": len(prepared.paragraphs),
        "approximate_tagging_input_tokens": approximate_input_tokens,
        "note": "Output and thinking tokens are provider-dependent and billed separately.",
    }


def embedding_token_count(text: str) -> int:
    """Count tokens using the encoding documented for OpenAI v3 embeddings."""

    return len(_embedding_encoding().encode(text))


@lru_cache(maxsize=1)
def _embedding_encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def _split_oversized_rows(
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    expanded: list[dict[str, object]] = []
    for row in rows:
        header = _text(row.get("header"), "header")
        content = _text(row.get("content"), "content")
        if embedding_token_count(f"## {header}\n\n{content}") <= _EMBEDDING_TOKEN_LIMIT:
            expanded.append(dict(row))
            continue
        parts = _split_content(header, content)
        part_count = len(parts)
        for part_index, part in enumerate(parts, start=1):
            expanded.append(
                {
                    **dict(row),
                    "content": part,
                    "part_index": part_index,
                    "part_count": part_count,
                }
            )
    return expanded


def _split_content(header: str, content: str) -> tuple[str, ...]:
    blocks = tuple(
        block.strip() for block in re.split(r"\n\s*\n", content) if block.strip()
    )
    parts: list[str] = []
    current: list[str] = []
    for block in blocks:
        candidate = "\n\n".join((*current, block))
        if (
            embedding_token_count(f"## {header}\n\n{candidate}")
            <= _EMBEDDING_SPLIT_TARGET
        ):
            current.append(block)
            continue
        if current:
            parts.append("\n\n".join(current))
            current = []
        if embedding_token_count(f"## {header}\n\n{block}") <= _EMBEDDING_SPLIT_TARGET:
            current.append(block)
            continue
        parts.extend(_split_large_block(header, block))
    if current:
        parts.append("\n\n".join(current))
    if not parts:
        raise ValueError("oversized chunk could not be split")
    return tuple(parts)


def _split_large_block(header: str, block: str) -> tuple[str, ...]:
    encoding = _embedding_encoding()
    header_tokens = len(encoding.encode(f"## {header}\n\n"))
    budget = _EMBEDDING_SPLIT_TARGET - header_tokens
    if budget < 1:
        raise ValueError("chunk header leaves no embedding token budget")
    tokens = encoding.encode(block)
    return tuple(
        encoding.decode(tokens[offset : offset + budget]).strip()
        for offset in range(0, len(tokens), budget)
        if tokens[offset : offset + budget]
    )


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-blank text")
    return value.strip()


def _optional_page(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer or null")
    return value


if __name__ == "__main__":
    main()
