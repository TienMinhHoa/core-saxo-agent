"""JSON/file adapter for full-fidelity knowledge metadata."""

from __future__ import annotations

import json
import hashlib
import os
import tempfile
from pathlib import Path

import anyio

from saxophone.documents.knowledge import KnowledgeChunk
from saxophone.platform.concurrency import create_blocking_io_limiter


class JsonKnowledgeRepository:
    """Persist one validated knowledge chunk per deterministic JSON sidecar."""

    def __init__(
        self,
        root: Path,
        *,
        io_limiter: anyio.CapacityLimiter | None = None,
    ) -> None:
        if not isinstance(root, Path):
            raise ValueError("root must be a Path")
        _reject_symbolic_link_in_path(root)
        resolved_root = root.resolve()
        if resolved_root.exists() and not resolved_root.is_dir():
            raise ValueError("root must be a directory")
        self._root = resolved_root
        self._io_limiter = io_limiter or create_blocking_io_limiter()

    async def upsert(self, chunk: KnowledgeChunk) -> None:
        await anyio.to_thread.run_sync(
            self._write,
            chunk,
            limiter=self._io_limiter,
        )

    async def get(self, chunk_id: str) -> KnowledgeChunk:
        payload = await anyio.to_thread.run_sync(
            self._read,
            chunk_id,
            limiter=self._io_limiter,
        )
        chunk = KnowledgeChunk(**payload)
        if chunk.chunk_id != chunk_id:
            raise ValueError("stored chunk ID does not match requested chunk ID")
        return chunk

    async def delete(self, chunk_id: str) -> None:
        await anyio.to_thread.run_sync(
            self._path_for(chunk_id).unlink,
            limiter=self._io_limiter,
        )

    def _write(self, chunk: KnowledgeChunk) -> None:
        _reject_symbolic_link_in_path(self._root)
        self._root.mkdir(parents=True, exist_ok=True)
        payload = {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "source_version": chunk.source_version,
            "source_ref": chunk.source_ref,
            "search_text": chunk.search_text,
            "content_hash": chunk.content_hash,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "heading_path": list(chunk.heading_path),
            "tags": list(chunk.tags),
            "image_refs": list(chunk.image_refs),
            "paragraph_count": chunk.paragraph_count,
            "image_count": chunk.image_count,
        }
        _write_json_atomically(self._path_for(chunk.chunk_id), payload)

    def _read(self, chunk_id: str) -> dict[str, object]:
        with self._path_for(chunk_id).open(encoding="utf-8") as stored:
            payload = json.load(stored)
        if not isinstance(payload, dict):
            raise ValueError("knowledge sidecar must contain a JSON object")
        for field_name in ("heading_path", "tags", "image_refs"):
            values = payload.get(field_name)
            if not isinstance(values, list):
                raise ValueError(f"knowledge sidecar field {field_name} must be a JSON array")
            payload[field_name] = tuple(values)
        return payload

    def _path_for(self, chunk_id: str) -> Path:
        _reject_symbolic_link_in_path(self._root)
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("chunk_id must not be blank")
        digest = hashlib.sha256(chunk_id.encode("utf-8")).hexdigest()
        return self._root / f"{digest}.json"


def _write_json_atomically(path: Path, payload: object) -> None:
    _reject_symbolic_link_in_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_symbolic_link_in_path(path)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temporary:
            json.dump(payload, temporary, ensure_ascii=False, sort_keys=True)
            temporary.flush()
            os.fsync(temporary.fileno())
        _reject_symbolic_link_in_path(path)
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _reject_symbolic_link_in_path(path: Path) -> None:
    """Reject a root whose explicit path crosses a symbolic-link component."""

    absolute_path = path.absolute()
    current = Path(absolute_path.anchor)
    for component in absolute_path.parts[1:]:
        current /= component
        if current.is_symlink():
            if current == absolute_path:
                raise ValueError("root must not be a symbolic link")
            raise ValueError("root path must not contain a symbolic link")
