from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from music_rag.contracts import validate_decision
from music_rag.errors import ValidationError
from music_rag.importer import import_markdown
from music_rag.manifest import apply_manifest, validate_manifest_against_catalog
from music_rag.search import build_index
from music_rag.service import MusicMaterialService
from music_rag.store import CatalogStore


class MusicRagTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.root = Path(self.temp.name)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        (self.assets / "score.jpg").write_bytes(b"approved score bytes")
        (self.assets / "chart.jpg").write_bytes(b"chart is an asset too")
        self.markdown = self.root / "book.md"
        self.markdown.write_text(
            "# Sample Book\n\n"
            "<div style=\"text-align:center\">AUTHOR'S NOTES</div>\n"
            "Use the indicated symbols.\n\n"
            "# MAJOR SCALES - POLYTONAL VARIATIONS\n"
            "(see author's notes)\n"
            "<div><img src=\"score.jpg\" alt=\"Image\" /></div>\n"
            "![Image](chart.jpg)\n",
            encoding="utf-8",
        )
        self.store = CatalogStore(self.root / "catalog")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _import(self):
        return import_markdown(self.store, self.markdown, asset_root=self.assets, author="Example")

    def _approved_manifest(self) -> dict:
        report = self._import()
        catalog = self.store.load()
        blocks = sorted(catalog["blocks"].values(), key=lambda block: block["source_order"])
        notes_heading = next(block for block in blocks if block["raw_text"] == "AUTHOR'S NOTES")
        notes_text = next(block for block in blocks if block["raw_text"] == "Use the indicated symbols.")
        poly_heading = next(block for block in blocks if "POLYTONAL" in block["raw_text"])
        see_notes = next(block for block in blocks if "see author's notes" in block["raw_text"])
        score = next(block for block in blocks if block["asset_ref"] == "score.jpg")
        chart = next(block for block in blocks if block["asset_ref"] == "chart.jpg")
        sections = catalog["sections"]
        notes_section = next(section for section in sections.values() if section["heading_block_id"] == notes_heading["block_id"])
        poly_section = next(section for section in sections.values() if section["heading_block_id"] == poly_heading["block_id"])
        return {
            "document_id": report.document_id,
            "source_version": report.source_version,
            "items": [
                {
                    "item_id": "authors_notes", "item_version": 1, "section_id": notes_section["section_id"],
                    "item_type": "guideline", "content_block_ids": [notes_heading["block_id"], notes_text["block_id"]],
                    "required_context_refs": [], "verified_fields": {}, "review_status": "approved",
                },
                {
                    "item_id": "polytonal_group", "item_version": 1, "section_id": poly_section["section_id"],
                    "item_type": "exercise_group", "content_block_ids": [poly_heading["block_id"], see_notes["block_id"], score["block_id"], chart["block_id"]],
                    "required_context_refs": [{"item_id": "authors_notes", "item_version": 1, "evidence_block_id": see_notes["block_id"]}],
                    "verified_fields": {}, "review_status": "approved",
                },
            ],
        }

    def test_import_keeps_html_markdown_and_chart_assets_with_null_page_locator(self) -> None:
        report = self._import()
        self.assertTrue(report.imported)
        self.assertEqual(report.asset_references, 2)
        self.assertFalse(report.missing_assets)
        blocks = self.store.load()["blocks"].values()
        assets = [block for block in blocks if block["kind"] == "asset"]
        self.assertEqual({block["asset_ref"] for block in assets}, {"score.jpg", "chart.jpg"})
        self.assertTrue(all(block["locator"]["page_index"] is None for block in assets))
        self.assertTrue(any(section["title_raw"] == "AUTHOR'S NOTES" for section in self.store.load()["sections"].values()))

    def test_optional_paddle_json_maps_only_an_unambiguous_exact_source_block(self) -> None:
        layout = self.root / "layout"
        layout.mkdir()
        (layout / "page-0003.json").write_text(json.dumps({
            "page_index": 2, "width": 100, "height": 200,
            "coordinate_space": {"name": "raw_pdf_raster_pixels", "transform_to_source": "identity"},
            "parsing_res_list": [{"block_id": 8, "block_label": "text", "block_order": 3, "block_bbox": [90, 90, 99, 99], "source_bbox": [1, 2, 30, 40], "block_content": "Use the indicated symbols."}],
        }), encoding="utf-8")
        report = import_markdown(self.store, self.markdown, asset_root=self.assets, layout_json_dir=layout)
        block = next(block for block in self.store.load()["blocks"].values() if block["raw_text"] == "Use the indicated symbols.")
        self.assertEqual(block["locator"]["page_index"], 2)
        self.assertEqual(block["locator"]["bbox"], [1, 2, 30, 40])
        asset = next(block for block in self.store.load()["blocks"].values() if block["asset_ref"] == "score.jpg")
        self.assertIsNone(asset["locator"]["page_index"])

    def test_publish_search_select_and_render_preserve_complete_source_bundle(self) -> None:
        manifest = self._approved_manifest()
        self.assertEqual(validate_manifest_against_catalog(self.store, manifest), [])
        self.assertEqual(apply_manifest(self.store, manifest), [])
        self.assertEqual(build_index(self.store)["indexed"], 2)
        service = MusicMaterialService(self.store)
        hits = service.search_materials("gam trưởng đa điệu", "private")
        self.assertEqual(hits[0]["item_id"], "polytonal_group")
        candidates = service.get_material_candidates(hits, "private")
        selection = {
            "status": "selected", "candidate_set_id": candidates["candidate_set_id"],
            "selected_items": [{"item_id": "polytonal_group", "item_version": 1}],
            "evidence_block_ids": [candidates["candidates"][0]["evidence_block_ids"][0]],
        }
        response = service.build_source_response(selection, "private")
        self.assertFalse(response["ui"]["generated_answer"])
        self.assertEqual([item["item_id"] for item in response["items"]], ["authors_notes", "polytonal_group"])
        exercise = response["items"][1]
        self.assertEqual([block["kind"] for block in exercise["blocks"]], ["heading", "text", "asset", "asset"])
        self.assertEqual(exercise["blocks"][1]["text"], "(see author's notes)")
        self.assertNotIn("asset_path", exercise["blocks"][2])

    def test_renderer_escapes_untrusted_html_without_rewriting_source_text(self) -> None:
        self.markdown.write_text("# Source\n<script>not executable</script>\n", encoding="utf-8")
        report = self._import()
        catalog = self.store.load()
        blocks = sorted(catalog["blocks"].values(), key=lambda block: block["source_order"])
        heading, text = blocks
        section = next(section for section in catalog["sections"].values() if section["heading_block_id"] == heading["block_id"])
        manifest = {"document_id": report.document_id, "source_version": report.source_version, "items": [{
            "item_id": "safe", "item_version": 1, "section_id": section["section_id"], "item_type": "guideline",
            "content_block_ids": [heading["block_id"], text["block_id"]], "required_context_refs": [], "verified_fields": {}, "review_status": "approved",
        }]}
        self.assertEqual(apply_manifest(self.store, manifest), [])
        build_index(self.store)
        service = MusicMaterialService(self.store)
        candidates = service.get_material_candidates(service.search_materials("source", "private"), "private")
        response = service.build_source_response({"status": "selected", "candidate_set_id": candidates["candidate_set_id"], "selected_items": [{"item_id": "safe", "item_version": 1}], "evidence_block_ids": [heading["block_id"]]}, "private")
        self.assertEqual(response["items"][0]["blocks"][1]["text"], "&lt;script&gt;not executable&lt;/script&gt;")

    def test_decision_contract_rejects_generated_text_stale_versions_and_foreign_evidence(self) -> None:
        candidates = {"candidate_set_id": "set", "candidates": [{"item_id": "one", "item_version": 1, "evidence_block_ids": ["block_one"]}]}
        base = {"status": "selected", "candidate_set_id": "set", "selected_items": [{"item_id": "one", "item_version": 1}], "evidence_block_ids": ["block_one"]}
        self.assertEqual(validate_decision(base, candidates), base)
        for invalid in (
            {**base, "answer": "Here is your exercise"},
            {**base, "selected_items": [{"item_id": "one", "item_version": 2}]},
            {**base, "evidence_block_ids": ["foreign"]},
        ):
            with self.assertRaises(ValidationError):
                validate_decision(invalid, candidates)

    def test_missing_asset_stays_draft_and_cannot_be_published_or_indexed(self) -> None:
        self.markdown.write_text("# Missing\n<img src=\"not-there.jpg\" />\n", encoding="utf-8")
        report = self._import()
        self.assertEqual(report.missing_assets, ["not-there.jpg"])
        catalog = self.store.load()
        heading = next(block for block in catalog["blocks"].values() if block["kind"] == "heading")
        asset = next(block for block in catalog["blocks"].values() if block["kind"] == "asset")
        section = next(section for section in catalog["sections"].values() if section["heading_block_id"] == heading["block_id"])
        manifest = {"document_id": report.document_id, "source_version": report.source_version, "items": [{
            "item_id": "missing", "item_version": 1, "section_id": section["section_id"], "item_type": "exercise",
            "content_block_ids": [heading["block_id"], asset["block_id"]], "required_context_refs": [], "verified_fields": {}, "review_status": "approved",
        }]}
        self.assertIn("missing:1:asset_missing", validate_manifest_against_catalog(self.store, manifest))
        self.assertEqual(build_index(self.store)["indexed"], 0)

    def test_scope_is_checked_during_search_fetch_and_asset_delivery(self) -> None:
        manifest = self._approved_manifest()
        self.assertEqual(apply_manifest(self.store, manifest), [])
        build_index(self.store)
        service = MusicMaterialService(self.store)
        self.assertEqual(service.search_materials("polytonal", "other"), [])
        catalog = self.store.load()
        score = next(block for block in catalog["blocks"].values() if block["asset_ref"] == "score.jpg")
        with self.assertRaises(Exception):
            service.asset_path("polytonal_group", 1, score["block_id"], "other")

    def test_changed_asset_checksum_is_removed_from_the_index(self) -> None:
        self.assertEqual(apply_manifest(self.store, self._approved_manifest()), [])
        (self.assets / "score.jpg").write_bytes(b"tampered")
        result = build_index(self.store)
        self.assertEqual(result, {"indexed": 1, "skipped": 1})


class ReadOnlySampleTest(unittest.TestCase):
    def test_actual_saxophone_markdown_has_184_asset_references_when_available(self) -> None:
        root = Path(__file__).resolve().parents[1]
        markdown = root / "output" / "Technique of the Saxophone Vol 1 - Scale Studies" / "Technique of the Saxophone Vol 1 - Scale Studies.md"
        assets = root / "output"
        if not markdown.is_file():
            self.skipTest("sample source is not available")
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            report = import_markdown(CatalogStore(temporary), markdown, asset_root=assets)
        self.assertEqual(report.asset_references, 184)
        self.assertEqual(len(report.missing_assets), 184)


if __name__ == "__main__":
    unittest.main()
