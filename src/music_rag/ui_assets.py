"""Asset allow-list policy used by the compatibility Gradio UI."""

from __future__ import annotations

from pathlib import Path

from .service import MusicMaterialService
from .store import CatalogStore
from .util import require_within


def approved_asset_paths(catalog_path: str | Path, access_scope: str) -> list[str]:
    """Return only approved asset files inside their document roots.

    The UI uses this result as a static-file allow-list.  The policy belongs
    beside the catalog service rather than in the legacy root entrypoint.
    """
    service = MusicMaterialService(CatalogStore(Path(catalog_path)))
    catalog = service.store.load()
    paths: set[str] = set()
    for item in catalog["items"].values():
        if item.get("review_status") != "approved":
            continue
        document = catalog["documents"].get(f"{item['document_id']}:{item['source_version']}")
        if document is None or document.get("access_scope") != access_scope:
            continue
        for block_id in item["content_block_ids"]:
            try:
                block = catalog["blocks"][block_id]
                if block.get("kind") != "asset" or not block.get("asset_path"):
                    continue
                path = require_within(Path(document["asset_root"]), Path(block["asset_path"]))
                if path.is_file():
                    paths.add(str(path))
            except (KeyError, ValueError):
                continue
    return sorted(paths)
