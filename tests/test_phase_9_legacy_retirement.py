"""Deletion gates for retiring the legacy music-RAG compatibility runtime.

These tests describe the agreed target: the deployable backend is the
``saxophone`` package and its ``saxophone-api`` command.  They intentionally
fail until the legacy Catalog/Gradio implementation is removed without
reintroducing a second runtime path.
"""

from __future__ import annotations

import ast
from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
BACKEND_ROOT = SOURCE_ROOT / "saxophone"
RETIRED_PATHS = (
    PROJECT_ROOT / "app.py",
    SOURCE_ROOT / "pdf_layout_web.py",
    SOURCE_ROOT / "music_rag",
    SOURCE_ROOT / "extracted",
    BACKEND_ROOT / "retrieval" / "legacy.py",
)
RETIRED_IMPORT_ROOTS = frozenset({"music_rag", "pdf_layout_web", "extracted"})


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_retired_legacy_runtime_paths_are_absent() -> None:
    """No obsolete launcher, compatibility module, package, or bridge remains."""

    remaining = []
    for path in RETIRED_PATHS:
        if path.is_dir():
            remaining.extend(child.relative_to(PROJECT_ROOT) for child in path.rglob("*.py"))
        elif path.exists():
            remaining.append(path.relative_to(PROJECT_ROOT))

    assert remaining == []


def test_backend_source_has_no_retired_runtime_imports() -> None:
    """The new backend must not depend on a compatibility implementation."""

    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(_import_roots(path) & RETIRED_IMPORT_ROOTS)
        for path in BACKEND_ROOT.rglob("*.py")
        if _import_roots(path) & RETIRED_IMPORT_ROOTS
    }

    assert violations == {}


def test_packaging_contains_only_the_backend_runtime() -> None:
    """A standard install exposes one backend package and one web command."""

    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"] == {"saxophone-api": "saxophone.main:main"}
    assert "legacy-ui" not in pyproject["project"].get("optional-dependencies", {})
    assert pyproject["tool"]["setuptools"].get("py-modules", []) == []
    assert pyproject["tool"]["setuptools"]["packages"]["find"]["include"] == ["saxophone*"]


def test_primary_runbook_does_not_advertise_retired_legacy_runtime() -> None:
    """Operators are guided only to the supported FastAPI backend command."""

    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "saxophone-api" in readme
    assert "Gradio" not in readme
    assert "music-rag" not in readme
    assert "legacy-ui" not in readme
