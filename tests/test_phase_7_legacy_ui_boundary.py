"""Keep pure compatibility-UI policy outside the root entrypoint."""

from __future__ import annotations

import ast
from pathlib import Path


def test_ui_rendering_exposes_only_pure_policy_helpers() -> None:
    from music_rag.ui_rendering import __all__

    assert set(__all__) == {
        "chroma_asset_paths",
        "display_status",
        "format_answer_cost",
        "render_chroma_results",
        "render_source_bundle",
    }


def test_root_entrypoint_delegates_status_and_asset_policy() -> None:
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "music_rag.ui_rendering"
    }

    assert imports == {"music_rag.ui_rendering"}


def test_root_entrypoint_does_not_redefine_ui_policy_helpers() -> None:
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    definitions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert definitions.isdisjoint(
        {
            "display_status",
            "chroma_asset_paths",
            "render_chroma_results",
            "render_source_bundle",
            "_chroma_image_path",
        }
    )


def test_root_entrypoint_has_no_dead_legacy_ui_aliases() -> None:
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert imported_names.isdisjoint(
        {"MusicMaterialService", "_display_status", "_render_source_bundle"}
    )
