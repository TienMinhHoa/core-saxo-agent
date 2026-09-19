from __future__ import annotations

import json
from pathlib import Path

from extracted.extract_header_chunks import extract_chunks


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "golden" / "header_chunks"


def test_page_aware_header_chunks_match_the_approved_golden_fixture() -> None:
    """Lock the current header-chunk/page provenance contract before migration."""
    source = (FIXTURE_DIR / "page_aware_sections.md").read_text(encoding="utf-8")
    expected = json.loads((FIXTURE_DIR / "page_aware_sections.expected.json").read_text(encoding="utf-8"))

    assert extract_chunks(source) == expected
