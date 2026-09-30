from __future__ import annotations

import subprocess
import sys


def test_tagging_wildcard_import_keeps_implementation_modules_lazy() -> None:
    """Wildcard tagging imports expose contracts without loading adapters."""

    script = """
import importlib
import sys

package = importlib.import_module("saxophone.tagging")
implementation_modules = (
    "saxophone.tagging.adapters",
    "saxophone.tagging.persistence",
    "saxophone.tagging.parser",
    "saxophone.tagging.use_cases",
)
assert all(name not in sys.modules for name in implementation_modules)

namespace = {}
exec("from saxophone.tagging import *", namespace)

assert {
    "ExistingTagCandidate",
    "ParagraphBlock",
    "ParagraphConceptRole",
    "TagConflictResolution",
    "TagGenerationRequest",
    "TaggedParagraph",
    "ConceptCandidate",
    "ChunkTagger",
} <= namespace.keys()
assert all(name not in namespace for name in (
    "JsonTagCatalogRepository",
    "JsonTaggedParagraphRepository",
    "RemoteParagraphTagger",
    "RemoteTagConflictResolver",
    "TagAndPersistParagraph",
    "TagParagraph",
    "parse_chunk_paragraphs",
))
assert all(name not in sys.modules for name in implementation_modules)
"""
    subprocess.run([sys.executable, "-c", script], check=True)


def test_tagging_facade_preserves_explicit_implementation_imports() -> None:
    """Explicit compatibility imports still resolve through the lazy facade."""

    import saxophone.tagging as package

    assert package.JsonTagCatalogRepository.__module__ == "saxophone.tagging.persistence"
    assert package.RemoteParagraphTagger.__module__ == "saxophone.tagging.adapters"
    assert package.TagParagraph.__module__ == "saxophone.tagging.use_cases"
    assert package.parse_chunk_paragraphs.__module__ == "saxophone.tagging.parser"
