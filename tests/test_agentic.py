from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from music_rag.agentic import AgenticRetriever
from music_rag.bootstrap import chapter_manifest
from music_rag.importer import import_markdown
from music_rag.manifest import apply_manifest
from music_rag.semantic import build_semantic_index
from music_rag.service import MusicMaterialService
from music_rag.store import CatalogStore


class FakeEmbeddings:
    model = "agent-test-embedding"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class ScriptedAgent:
    def __init__(self, select_on: int | None) -> None:
        self.select_on = select_on
        self.assessments = 0
        self.rewrites: list[tuple[str, str]] = []

    def assess(self, request: str, candidates: list[dict]) -> int | None:
        self.assessments += 1
        return 0 if self.select_on == self.assessments and candidates else None

    def rewrite(self, request: str, previous_query: str, aspect: str) -> str:
        self.rewrites.append((previous_query, aspect))
        return f"{request} {aspect}"


class AgenticRagTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        root = Path(self.temp.name)
        source = root / "book.md"
        source.write_text("# Chapter 1 Rhythm\nRhythm is pulse.\n", encoding="utf-8")
        self.store = CatalogStore(root / "catalog")
        report = import_markdown(self.store, source, asset_root=root, access_scope="public")
        self.assertEqual(apply_manifest(self.store, chapter_manifest(self.store, report, approved=True)), [])
        self.provider = FakeEmbeddings()
        build_semantic_index(self.store, self.provider)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_retries_four_rounds_and_returns_final_round_best_source(self) -> None:
        agent = ScriptedAgent(select_on=None)
        result = AgenticRetriever(MusicMaterialService(self.store), self.provider, agent, max_rounds=4).run("unmet request", "public")
        self.assertEqual(result.status, "no_match_best_effort")
        self.assertEqual(result.rounds, 4)
        self.assertEqual(agent.assessments, 4)
        self.assertEqual(len(agent.rewrites), 3)
        self.assertEqual(result.response["items"][0]["item_id"], "chapter_01")
        self.assertFalse(result.response["ui"]["generated_answer"])

    def test_selecting_in_second_round_stops_remaining_retries(self) -> None:
        agent = ScriptedAgent(select_on=2)
        result = AgenticRetriever(MusicMaterialService(self.store), self.provider, agent, max_rounds=4).run("rhythm", "public")
        self.assertEqual(result.status, "selected")
        self.assertEqual(result.rounds, 2)
        self.assertEqual(len(agent.rewrites), 1)

    def test_configured_rounds_are_capped_at_four(self) -> None:
        self.assertEqual(AgenticRetriever(MusicMaterialService(self.store), self.provider, ScriptedAgent(None), max_rounds=99).max_rounds, 4)


if __name__ == "__main__":
    unittest.main()
