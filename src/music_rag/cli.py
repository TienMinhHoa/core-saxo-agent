"""Command-line entry points for import, review-manifest validation and demo."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from .bootstrap import import_chapter_demo
from .embeddings import OpenAIEmbeddingProvider
from .importer import import_markdown
from .manifest import apply_manifest, validate_manifest_against_catalog
from .search import build_index
from .semantic import build_semantic_index
from .service import MusicMaterialService
from .store import CatalogStore


def _json_path(value: str) -> dict:
    return json.loads(Path(value).read_text(encoding="utf-8"))


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True, help="Writable catalog directory; never a source directory")
    commands = parser.add_subparsers(dest="command", required=True)
    draft = commands.add_parser("draft-import")
    draft.add_argument("markdown", type=Path)
    draft.add_argument("--asset-root", type=Path, required=True)
    draft.add_argument("--title")
    draft.add_argument("--author")
    draft.add_argument("--access-scope", default="private")
    draft.add_argument("--layout-json-dir", type=Path, help="Optional Paddle per-page JSON directory")
    validate = commands.add_parser("validate-manifest")
    validate.add_argument("manifest", type=_json_path)
    publish = commands.add_parser("apply-manifest")
    publish.add_argument("manifest", type=_json_path)
    commands.add_parser("build-index")
    semantic = commands.add_parser("build-semantic-index")
    semantic.add_argument("--batch-size", type=int, default=32)
    bootstrap = commands.add_parser("bootstrap-music-theory-demo")
    bootstrap.add_argument("markdown", type=Path)
    bootstrap.add_argument("--asset-root", type=Path, required=True)
    bootstrap.add_argument("--manifest-output", type=Path, required=True)
    bootstrap.add_argument("--operator-approves", action="store_true", help="Explicit operator attestation for demo chapter boundaries")
    demo = commands.add_parser("demo-search")
    demo.add_argument("query")
    demo.add_argument("--access-scope", default="private")
    args = parser.parse_args()
    store = CatalogStore(args.catalog)
    if args.command == "draft-import":
        result = import_markdown(store, args.markdown, asset_root=args.asset_root, title=args.title, author=args.author, access_scope=args.access_scope, layout_json_dir=args.layout_json_dir).as_dict()
    elif args.command == "validate-manifest":
        result = {"errors": validate_manifest_against_catalog(store, args.manifest)}
    elif args.command == "apply-manifest":
        result = {"errors": apply_manifest(store, args.manifest)}
    elif args.command == "build-index":
        result = build_index(store)
    elif args.command == "build-semantic-index":
        result = build_semantic_index(store, OpenAIEmbeddingProvider(), batch_size=args.batch_size)
    elif args.command == "bootstrap-music-theory-demo":
        report, manifest = import_chapter_demo(store, str(args.markdown), str(args.asset_root), approved=args.operator_approves)
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = {"import": report.as_dict(), "manifest": str(args.manifest_output), "items": len(manifest["items"]), "errors": apply_manifest(store, manifest)}
    else:
        service = MusicMaterialService(store)
        hits = service.search_materials(args.query, args.access_scope)
        result = {"hits": hits, "candidate_set": service.get_material_candidates(hits, args.access_scope)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
