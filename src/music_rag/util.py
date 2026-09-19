"""Small dependency-free utilities shared by the catalog components."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}_{sha256_bytes(payload)[:20]}"


def normalise_for_search(value: str) -> str:
    """Normalise only the search representation; never use this for render."""
    return re.sub(r"\s+", " ", value.casefold()).strip()


def tokens(value: str) -> set[str]:
    return set(re.findall(r"[\w]+", normalise_for_search(value), flags=re.UNICODE))


def require_within(root: Path, candidate: Path) -> Path:
    """Resolve a local asset while rejecting traversal and escaping symlinks."""
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("asset_path_outside_root") from exc
    return resolved_candidate


def ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    return [value for value in values if not (value in seen or seen.add(value))]
