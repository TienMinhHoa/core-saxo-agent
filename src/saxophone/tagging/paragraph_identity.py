"""Stable identity helpers for source-preserving paragraph references."""

from __future__ import annotations

import hashlib
import re
import unicodedata


_WHITESPACE = re.compile(r"\s+")


def normalized_identity(text: str) -> str:
    """Normalize only identity noise; return source text unchanged elsewhere."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must not be blank")
    normalized = unicodedata.normalize("NFKC", text)
    return _WHITESPACE.sub(" ", normalized).strip().casefold()


def identity_digest(text: str, *, length: int = 12) -> str:
    """Return a compact digest suitable for a stable paragraph reference."""
    if length < 8:
        raise ValueError("length must be at least 8")
    return hashlib.sha256(normalized_identity(text).encode("utf-8")).hexdigest()[:length]


def paragraph_reference(chunk_id: str, text: str, duplicate_occurrence: int) -> str:
    """Build a reference from chunk identity, normalized content, and occurrence."""
    if not isinstance(chunk_id, str) or not chunk_id.strip():
        raise ValueError("chunk_id must not be blank")
    if duplicate_occurrence < 1:
        raise ValueError("duplicate_occurrence must be positive")
    return f"{chunk_id.strip()}:{identity_digest(text)}:{duplicate_occurrence}"
