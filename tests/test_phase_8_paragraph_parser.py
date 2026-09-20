from __future__ import annotations

from saxophone.ingestion.models import IngestionSourceChunk
from saxophone.tagging.parser import parse_chunk_paragraphs


def _chunk(text: str) -> IngestionSourceChunk:
    return IngestionSourceChunk(
        chunk_id="chunk-1",
        document_ref="doc-1",
        source_version="extract-v1",
        search_text=text,
        access_scope="private",
        metadata={"heading": "Harmony"},
    )


def test_parser_preserves_source_order_text_and_nested_heading_context() -> None:
    paragraphs = parse_chunk_paragraphs(_chunk("""## Page 2
### Definition
First paragraph.

Second paragraph.
"""))

    assert [paragraph.text for paragraph in paragraphs] == ["First paragraph.", "Second paragraph."]
    assert [paragraph.ordinal for paragraph in paragraphs] == [0, 1]
    assert paragraphs[0].heading_path == ("Definition",)
    assert paragraphs[0].paragraph_id == parse_chunk_paragraphs(_chunk("""## Page 2
### Definition
First paragraph.

Second paragraph.
"""))[0].paragraph_id


def test_parser_detects_markdown_and_html_images_and_links_captions() -> None:
    paragraphs = parse_chunk_paragraphs(
        _chunk("A figure explains the cadence. ![figure](images/cadence.png)\n\n<img src='images/score.png'>"),
        image_metadata={"images/cadence.png": {"caption": "Cadence diagram"}},
    )

    assert paragraphs[0].image_refs == ("images/cadence.png", "images/score.png")
    assert paragraphs[0].image_captions == {"images/cadence.png": "Cadence diagram"}


def test_parser_does_not_turn_page_markers_or_image_only_blocks_into_knowledge_paragraphs() -> None:
    paragraphs = parse_chunk_paragraphs(_chunk("""## Page 1
![figure](images/one.png)

Knowledge paragraph.
"""))

    assert len(paragraphs) == 1
    assert paragraphs[0].text == "Knowledge paragraph."
    assert paragraphs[0].image_refs == ("images/one.png",)
