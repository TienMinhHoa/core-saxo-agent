from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from music_rag.bootstrap import chapter_manifest
from music_rag.importer import import_markdown
from music_rag.manifest import apply_manifest
from music_rag.semantic import build_semantic_index, semantic_search
from music_rag.service import MusicMaterialService
from music_rag.store import CatalogStore


class FakeEmbeddings:
    model = "test-semantic-v1"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            lower = text.casefold()
            vectors.append([1.0, 0.0] if any(word in lower for word in ("rhythm", "beat", "pulse", "count")) else [0.0, 1.0])
        return vectors


class SemanticRagTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.root = Path(self.temp.name)
        self.source = self.root / "book.md"
        self.source.write_text(
            "# Chapter 1 Rhythm\nRhythm is a pattern of regular pulses.\n"
            "# Chapter 2 Harmony\nChords create harmony.\n",
            encoding="utf-8",
        )
        self.store = CatalogStore(self.root / "catalog")
        self.report = import_markdown(self.store, self.source, asset_root=self.root, access_scope="public")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_semantic_search_selects_item_and_returns_source_not_generated_text(self) -> None:
        manifest = chapter_manifest(self.store, self.report, approved=True)
        self.assertEqual(len(manifest["items"]), 2)
        self.assertEqual(apply_manifest(self.store, manifest), [])
        provider = FakeEmbeddings()
        self.assertEqual(build_semantic_index(self.store, provider)["indexed"], 2)
        hits = semantic_search(self.store, provider, "How do I count a pulse?", "public")
        self.assertEqual(hits[0]["item_id"], "chapter_01")
        service = MusicMaterialService(self.store)
        candidates = service.get_material_candidates(hits, "public")
        decision = service.select_top_candidate(candidates)
        response = service.build_source_response(decision, "public")
        self.assertEqual(response["items"][0]["item_id"], "chapter_01")
        self.assertIn("Rhythm is a pattern of regular pulses.", response["items"][0]["blocks"][1]["text"])
        self.assertFalse(response["ui"]["generated_answer"])

    def test_draft_chapter_manifest_is_not_semantically_indexed(self) -> None:
        manifest = chapter_manifest(self.store, self.report, approved=False)
        self.assertEqual(apply_manifest(self.store, manifest), [])
        self.assertEqual(build_semantic_index(self.store, FakeEmbeddings())["indexed"], 0)


if __name__ == "__main__":
    unittest.main()
