from __future__ import annotations

import pytest

from saxophone.ingestion.chunking import build_source_chunks


def test_build_source_chunks_preserves_heading_content_and_page_metadata() -> None:
    chunks = build_source_chunks(
        """# Document\n\n## Harmony\n\n## Page 2\nA source paragraph.\n\n### Definition\nA nested paragraph.\n\n## Page 3\nA second paragraph.\n\n## Empty\n## Exercises\nTry this.""",
        document_ref="doc-1",
        source_version="extract-v1",
        access_scope="private",
    )

    assert [chunk.metadata["heading"] for chunk in chunks] == ["Harmony", "Exercises"]
    assert chunks[0].search_text == "A source paragraph.\n\n### Definition\nA nested paragraph.\n\nA second paragraph."
    assert chunks[0].metadata["page_start"] is None
    assert chunks[0].metadata["page_end"] == 3
    assert chunks[0].chunk_id.startswith("doc-1:extract-v1:0:")
    assert chunks[1].metadata["page_start"] == 3


def test_build_source_chunks_is_deterministic_and_scope_bound() -> None:
    markdown = "## Section\nContent"

    first = build_source_chunks(
        markdown,
        document_ref="doc-1",
        source_version="extract-v1",
        access_scope="private",
    )
    second = build_source_chunks(
        markdown,
        document_ref="doc-1",
        source_version="extract-v1",
        access_scope="private",
    )

    assert first == second
    assert first[0].document_ref == "doc-1"
    assert first[0].source_version == "extract-v1"
    assert first[0].access_scope == "private"


@pytest.mark.parametrize("heading_level", [0, 7])
def test_build_source_chunks_rejects_invalid_heading_level(heading_level: int) -> None:
    with pytest.raises(ValueError, match="heading_level"):
        build_source_chunks(
            "## Section\nContent",
            document_ref="doc-1",
            source_version="extract-v1",
            access_scope="private",
            heading_level=heading_level,
        )
