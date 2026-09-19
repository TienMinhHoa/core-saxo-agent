import json
import tempfile
import unittest
from pathlib import Path

from extracted.structure_markdown_with_llm import (
    Candidate,
    Label,
    build_chunks,
    build_nodes,
    find_candidates,
    label_all,
    render_markdown,
    validate_continuity,
)


class _FakeLabeler:
    model = "deepseek-flash"

    def __init__(self, labels):
        self.labels = {label.candidate_id: label for label in labels}
        self.calls = 0

    def label(self, candidates, outline, outline_reference):
        self.calls += 1
        return [self.labels[item.candidate_id] for item in candidates], {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_hit_tokens": 0,
            "cache_miss_tokens": 100,
            "reasoning_tokens": 20,
        }


class StructureMarkdownWithLlmTests(unittest.TestCase):
    def test_candidate_detection_uses_markdown_and_plain_uppercase_titles(self):
        markdown = """## Page 1
# Chapter 1
Body.
HEALTH & SELF-HELP
More body.
"""
        candidates = find_candidates(markdown)
        self.assertEqual([item.display_text for item in candidates], ["Chapter 1", "HEALTH & SELF-HELP"])
        self.assertIn("uppercase_short_line", candidates[1].evidence)

    def test_same_title_under_different_chapters_never_merges(self):
        markdown = """## Page 1
# Chapter 1
## In This Chapter
First body.
## Page 2
# Chapter 2
## In This Chapter
Second body.
"""
        candidates = find_candidates(markdown)
        by_text = {}
        for candidate in candidates:
            by_text.setdefault(candidate.display_text, []).append(candidate)
        labels = [
            Label(by_text["Chapter 1"][0].candidate_id, "chapter", 3, "Chapter 1", True, False, None),
            Label(by_text["In This Chapter"][0].candidate_id, "chapter_intro", 4, "In This Chapter", True, False, "Chapter 1"),
            Label(by_text["Chapter 2"][0].candidate_id, "chapter", 3, "Chapter 2", True, False, None),
            Label(by_text["In This Chapter"][1].candidate_id, "chapter_intro", 4, "In This Chapter", True, False, "Chapter 2"),
        ]
        labels.sort(key=lambda label: next(c.line_number for c in candidates if c.candidate_id == label.candidate_id))
        nodes = build_nodes(markdown, candidates, labels)
        chunks = build_chunks(markdown, candidates, labels, nodes)
        validate_continuity(chunks)
        intros = [chunk for chunk in chunks if chunk["title"] == "In This Chapter"]
        self.assertEqual(len(intros), 2)
        self.assertEqual(intros[0]["heading_path"], ["Chapter 1", "In This Chapter"])
        self.assertEqual(intros[1]["heading_path"], ["Chapter 2", "In This Chapter"])
        self.assertEqual(intros[0]["content"], "First body.")
        self.assertEqual(intros[1]["content"], "Second body.")

    def test_repeated_heading_marked_continuation_does_not_split(self):
        markdown = """## Page 1
## Long Topic
First paragraph.
## Page 2
## Long Topic
Second paragraph.
"""
        candidates = find_candidates(markdown)
        labels = [
            Label(candidates[0].candidate_id, "section", 4, "Long Topic", True, False, None),
            Label(candidates[1].candidate_id, "section", 4, "Long Topic", False, True, None),
        ]
        nodes = build_nodes(markdown, candidates, labels)
        chunks = build_chunks(markdown, candidates, labels, nodes)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["page_start"], 1)
        self.assertEqual(chunks[0]["page_end"], 2)
        self.assertEqual(chunks[0]["content"], "First paragraph.\n\nSecond paragraph.")

    def test_structural_role_wins_when_model_sets_starts_false(self):
        markdown = """## Page 1
# Chapter 1
## In This Chapter
Overview.
"""
        candidates = find_candidates(markdown)
        labels = [
            Label(candidates[0].candidate_id, "chapter", 3, "Chapter 1", True, False, None),
            Label(candidates[1].candidate_id, "chapter_intro", None, "In This Chapter", False, False, "Chapter 1"),
        ]
        nodes = build_nodes(markdown, candidates, labels)
        self.assertEqual([node.title for node in nodes], ["Chapter 1", "In This Chapter"])

    def test_appendix_closes_the_last_part(self):
        markdown = """## Page 1
# Part V
# Chapter 20
Body.
## Appendix A Reference
Appendix body.
"""
        candidates = find_candidates(markdown)
        labels = [
            Label(candidates[0].candidate_id, "part", 2, "Part V", True, False, None),
            Label(candidates[1].candidate_id, "chapter", 3, "Chapter 20", True, False, "Part V"),
            Label(candidates[2].candidate_id, "chapter", 3, "Appendix A: Reference", True, False, None),
        ]
        nodes = build_nodes(markdown, candidates, labels)
        self.assertIsNone(nodes[2].parent_id)
        self.assertEqual(nodes[2].level, 2)

    def test_empty_chapter_container_is_kept_for_markdown_outline(self):
        markdown = """## Page 1
# Chapter 1
## In This Chapter
Overview.
"""
        candidates = find_candidates(markdown)
        labels = [
            Label(candidates[0].candidate_id, "chapter", 3, "Chapter 1", True, False, None),
            Label(candidates[1].candidate_id, "chapter_intro", 4, "In This Chapter", True, False, "Chapter 1"),
        ]
        nodes = build_nodes(markdown, candidates, labels)
        chunks = build_chunks(markdown, candidates, labels, nodes)
        self.assertEqual([chunk["title"] for chunk in chunks], ["Chapter 1", "In This Chapter"])
        self.assertEqual(chunks[0]["content"], "")

    def test_resume_cache_avoids_rebilling_completed_batches(self):
        candidates = [
            Candidate(f"line-{n:06d}", n, 1, f"## H{n}", f"H{n}", 2, ["markdown_heading"], [], ["body"])
            for n in range(1, 4)
        ]
        labels = [Label(c.candidate_id, "section", 4, c.display_text, True, False, None) for c in candidates]
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "labels.json"
            first = _FakeLabeler(labels)
            output, requests = label_all(
                candidates, first, source_hash="abc", outline_reference="", cache_path=cache,
                batch_size=2, retries=0,
            )
            self.assertEqual(len(output), 3)
            self.assertEqual(first.calls, 2)
            second = _FakeLabeler(labels)
            output2, requests2 = label_all(
                candidates, second, source_hash="abc", outline_reference="", cache_path=cache,
                batch_size=2, retries=0,
            )
            self.assertEqual(output2, output)
            self.assertEqual(second.calls, 0)
            self.assertEqual(requests2, requests)
            payload = json.loads(cache.read_text())
            self.assertNotIn("confidence", json.dumps(payload))

    def test_renderer_adds_existing_vlm_caption_after_image(self):
        chunks = [{
            "title": "Topic", "heading_level": 4, "page_start": 2, "page_end": 2,
            "content": '<div><img src="images/a.jpg" /></div>',
        }]
        vlm = {"images/a.jpg": {"analysis": {"figure_number": "1-1", "figure_title": "Notes", "summary": "A staff."}}}
        rendered = render_markdown(chunks, source=Path("document.md"), vlm_results=vlm)
        self.assertIn("images/a.jpg", rendered)
        self.assertIn("1-1 — Notes", rendered)
        self.assertIn("Summary:</strong> A staff.", rendered)


if __name__ == "__main__":
    unittest.main()
