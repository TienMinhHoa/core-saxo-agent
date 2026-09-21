"""A tiny versioned JSON repository used by the MVP.

The store is intentionally transparent and portable.  Deployments can replace
this class with their existing repository while retaining the contract used by
the importer, validator, search service and renderer.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import NotFound


EMPTY_CATALOG: dict[str, Any] = {
    "documents": {},
    "blocks": {},
    "sections": {},
    "items": {},
    "search_units": {},
    "semantic_index": {},
}


class CatalogStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.path = self.root / "catalog.json"

    def load(self) -> dict[str, Any]:
        self._validate_paths()
        if not self.path.exists():
            return json.loads(json.dumps(EMPTY_CATALOG))
        with self.path.open(encoding="utf-8") as handle:
            catalog = json.load(handle)
        for key, value in EMPTY_CATALOG.items():
            catalog.setdefault(key, {} if isinstance(value, dict) else value)
        return catalog

    def save(self, catalog: dict[str, Any]) -> None:
        self._validate_paths()
        self.root.mkdir(parents=True, exist_ok=True)
        self._validate_paths()
        fd, temporary = tempfile.mkstemp(prefix="catalog-", suffix=".json", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(catalog, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temporary, self.path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def _validate_paths(self) -> None:
        _reject_symbolic_link_in_path(self.root)
        if self.root.exists() and not self.root.is_dir():
            raise ValueError("root must be a directory")
        _reject_symbolic_link_in_path(self.path)
        if self.path.exists() and not self.path.is_file():
            raise ValueError("catalog path must be a file")

    def document(self, document_id: str, source_version: str) -> dict[str, Any]:
        record = self.load()["documents"].get(f"{document_id}:{source_version}")
        if record is None:
            raise NotFound("document_version_not_found")
        return record


def _reject_symbolic_link_in_path(path: Path) -> None:
    """Reject explicit path components that could redirect JSON persistence."""

    absolute_path = path.absolute()
    current = Path(absolute_path.anchor)
    for component in absolute_path.parts[1:]:
        current /= component
        if current.is_symlink():
            raise ValueError("catalog path must not contain a symbolic link")
