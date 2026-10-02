from __future__ import annotations

import subprocess
import sys


def test_ingestion_wildcard_import_keeps_use_cases_lazy() -> None:
    """Wildcard imports should not pull application use cases or tagging adapters in."""

    script = """
import importlib
import sys

package = importlib.import_module("saxophone.ingestion")
optional_modules = (
    "saxophone.ingestion.use_cases",
    "saxophone.ingestion.services",
    "saxophone.ingestion.state",
    "saxophone.tagging.adapters",
    "saxophone.tagging.chunk_service",
    "saxophone.tagging.persistence",
)
assert all(name not in sys.modules for name in optional_modules)

namespace = {}
exec("from saxophone.ingestion import *", namespace)

assert {
    "ChunkIndexRecord",
    "EmbeddingProvider",
    "EmbeddingReuseStore",
    "IndexInputRecord",
    "IngestionCommand",
    "IngestionReport",
    "IngestionSourceChunk",
    "VectorIndex",
    "build_source_chunks",
} <= namespace.keys()
assert "IngestDocument" not in namespace
assert "IndexDocument" not in namespace
assert all(name not in sys.modules for name in optional_modules)
"""
    subprocess.run([sys.executable, "-c", script], check=True)


def test_ingestion_use_cases_still_resolve_through_explicit_imports() -> None:
    """Existing callers can request use-case implementations explicitly."""

    script = """
from saxophone.ingestion import IngestDocument, IndexDocument

assert IngestDocument.__module__ == "saxophone.ingestion.use_cases"
assert IndexDocument.__module__ == "saxophone.ingestion.use_cases"
"""
    subprocess.run([sys.executable, "-c", script], check=True)
