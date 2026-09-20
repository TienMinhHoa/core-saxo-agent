"""Local JSON adapters for tag sidecars and the tag catalog."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import anyio

from saxophone.platform.concurrency import create_blocking_io_limiter
from .models import TaggedParagraph


class JsonTaggedParagraphRepository:
    """Persist one source-preserving tagged paragraph per JSON sidecar."""

    def __init__(
        self,
        root: Path,
        *,
        io_limiter: anyio.CapacityLimiter | None = None,
    ) -> None:
        self._root = root.resolve()
        self._io_limiter = io_limiter or create_blocking_io_limiter()

    @property
    def root(self) -> Path:
        """Return the resolved sidecar root for composition diagnostics."""
        return self._root

    async def upsert(self, paragraph: TaggedParagraph) -> None:
        await anyio.to_thread.run_sync(
            self._write,
            paragraph,
            limiter=self._io_limiter,
        )

    async def get(self, paragraph_id: str) -> TaggedParagraph:
        payload = await anyio.to_thread.run_sync(
            self._read,
            paragraph_id,
            limiter=self._io_limiter,
        )
        paragraph = TaggedParagraph(**payload)
        if paragraph.paragraph_id != paragraph_id:
            raise ValueError("stored paragraph ID does not match requested paragraph ID")
        return paragraph

    async def delete(self, paragraph_id: str) -> None:
        path = self._path_for(paragraph_id)
        await anyio.to_thread.run_sync(path.unlink, limiter=self._io_limiter)

    def _write(self, paragraph: TaggedParagraph) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        payload = {
            "paragraph_id": paragraph.paragraph_id,
            "text": paragraph.text,
            "generated_tags": list(paragraph.generated_tags),
            "tags": list(paragraph.tags),
            "status": paragraph.status,
        }
        _write_json_atomically(self._path_for(paragraph.paragraph_id), payload)

    def _read(self, paragraph_id: str) -> dict[str, object]:
        with self._path_for(paragraph_id).open(encoding="utf-8") as stored:
            payload = json.load(stored)
        if not isinstance(payload, dict):
            raise ValueError("tagged paragraph sidecar must contain a JSON object")
        return payload

    def _path_for(self, paragraph_id: str) -> Path:
        if not isinstance(paragraph_id, str) or not paragraph_id.strip():
            raise ValueError("paragraph_id must not be blank")
        digest = hashlib.sha256(paragraph_id.encode("utf-8")).hexdigest()
        return self._root / f"{digest}.json"


class JsonTagCatalogRepository:
    """Persist a deduplicated, deterministic plain-English tag catalog."""

    def __init__(
        self,
        path: Path,
        *,
        io_limiter: anyio.CapacityLimiter | None = None,
    ) -> None:
        self._path = path.resolve()
        self._io_limiter = io_limiter or create_blocking_io_limiter()

    @property
    def path(self) -> Path:
        """Return the resolved catalog path for composition diagnostics."""
        return self._path

    async def add(self, tags: tuple[str, ...]) -> None:
        await anyio.to_thread.run_sync(self._add, tags, limiter=self._io_limiter)

    async def list(self) -> tuple[str, ...]:
        return await anyio.to_thread.run_sync(self._list, limiter=self._io_limiter)

    def _add(self, tags: tuple[str, ...]) -> None:
        current = set(self._list())
        current.update(tags)
        _write_json_atomically(self._path, sorted(current))

    def _list(self) -> tuple[str, ...]:
        if not self._path.exists():
            return ()
        with self._path.open(encoding="utf-8") as stored:
            payload = json.load(stored)
        if not isinstance(payload, list) or any(not isinstance(tag, str) for tag in payload):
            raise ValueError("tag catalog must contain a JSON string array")
        return tuple(sorted(set(payload)))


def _write_json_atomically(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temporary:
            json.dump(payload, temporary, ensure_ascii=False, sort_keys=True)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
