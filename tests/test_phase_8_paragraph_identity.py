from __future__ import annotations

import pytest

from saxophone.ingestion.models import IngestionSourceChunk
from saxophone.tagging.paragraph_identity import (
    exact_content_hash,
    identity_digest,
    normalized_identity_hash,
    paragraph_reference,
)
from saxophone.tagging.parser import parse_chunk_paragraphs


def _chunk(text: str) -> IngestionSourceChunk:
    return IngestionSourceChunk(
        chunk_id="chunk-1",
        document_ref="doc-1",
        source_version="extract-v1",
        search_text=text,
        access_scope="private",
        metadata={},
    )


def test_reference_uses_content_digest_and_duplicate_occurrence() -> None:
    paragraphs = parse_chunk_paragraphs(_chunk("Same text.\n\nSame  text."))

    assert paragraphs[0].paragraph_id == f"chunk-1:{identity_digest('Same text.')}:1"
    assert paragraphs[1].paragraph_id == f"chunk-1:{identity_digest('Same  text.')}:2"
    assert paragraphs[0].paragraph_id != paragraphs[1].paragraph_id


def test_reference_is_not_renumbered_when_another_paragraph_is_inserted() -> None:
    original = parse_chunk_paragraphs(_chunk("First.\n\nTarget."))[1].paragraph_id
    changed = parse_chunk_paragraphs(_chunk("Inserted.\n\nFirst.\n\nTarget."))[2].paragraph_id

    assert changed == original


def test_parser_exposes_exact_and_normalized_identity_hashes() -> None:
    paragraph = parse_chunk_paragraphs(_chunk("Same  text."))[0]

    assert paragraph.exact_content_hash == exact_content_hash(paragraph.text)
    assert paragraph.normalized_identity_hash == normalized_identity_hash(paragraph.text)


def test_paragraph_rejects_hashes_that_do_not_match_source_text() -> None:
    with pytest.raises(ValueError, match="exact_content_hash"):
        parse_chunk_paragraphs(_chunk("Text"))[0].__class__(
            paragraph_id="p-1",
            chunk_id="chunk-1",
            ordinal=0,
            text="Text",
            exact_content_hash="wrong",
        )


@pytest.mark.parametrize("occurrence", [0, -1])
def test_reference_rejects_invalid_duplicate_occurrence(occurrence: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        paragraph_reference("chunk-1", "Text", occurrence)
