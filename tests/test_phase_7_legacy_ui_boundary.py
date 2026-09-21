"""Keep pure compatibility-UI policy outside the root entrypoint."""

from __future__ import annotations

import ast
from pathlib import Path


def test_ui_rendering_exposes_only_pure_policy_helpers() -> None:
    from music_rag.ui_rendering import __all__

    assert set(__all__) == {"chroma_asset_paths", "display_status"}


def test_root_entrypoint_delegates_status_and_asset_policy() -> None:
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "music_rag.ui_rendering"
    }

    assert imports == {"music_rag.ui_rendering"}
