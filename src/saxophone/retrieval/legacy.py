"""Compatibility imports for the legacy catalog retrieval implementation."""

from __future__ import annotations

from music_rag.semantic import semantic_search as legacy_semantic_search
from music_rag.store import CatalogStore as LegacyCatalogStore

__all__ = ["LegacyCatalogStore", "legacy_semantic_search"]
