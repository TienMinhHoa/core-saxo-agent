from __future__ import annotations

import pytest

from saxophone.ingestion.models import IngestionCommand, IngestionSourceChunk
from saxophone.ingestion.use_cases import build_index_inputs
from saxophone.tagging.models import TaggedParagraph


def _command() -> IngestionCommand:
    return IngestionCommand(
        document_ref="doc-1",
        source_version="source-v1",
        chunking_profile="chunk-v1",
        tagging_profile="tag-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
    )


def _chunk() -> IngestionSourceChunk:
    return IngestionSourceChunk(
        chunk_id="chunk-1",
        document_ref="doc-1",
        source_version="source-v1",
        search_text="Source text stays unchanged.",
        access_scope="tenant-a",
        metadata={"heading": "Introduction"},
    )


def test_build_index_inputs_merges_tags_without_inventing_embedding() -> None:
    paragraph = TaggedParagraph(
        paragraph_id="chunk-1:p0000-digest",
        text="Source text stays unchanged.",
        generated_tags=("Music",),
        tags=("music", "phrase"),
        status="completed",
    )

    result = build_index_inputs(_command(), [_chunk()], {paragraph.paragraph_id: paragraph})

    assert result[0].search_text == "Source text stays unchanged."
    assert result[0].metadata["tags"] == ("music", "phrase")
    assert result[0].metadata["tagged_paragraph_ids"] == (paragraph.paragraph_id,)
    assert not hasattr(result[0], "embedding")


def test_build_index_inputs_keeps_chunk_with_no_tagged_paragraphs() -> None:
    result = build_index_inputs(_command(), [_chunk()], {})

    assert len(result) == 1
    assert result[0].metadata["tags"] == ()
    assert result[0].metadata["tagged_paragraph_ids"] == ()


@pytest.mark.parametrize("field", ["document_ref", "source_version", "access_scope"])
def test_build_index_inputs_rejects_cross_scope_chunk(field: str) -> None:
    values = {"document_ref": "doc-1", "source_version": "source-v1", "access_scope": "tenant-a"}
    values[field] = "other"
    chunk = IngestionSourceChunk(
        chunk_id="chunk-1",
        document_ref=values["document_ref"],
        source_version=values["source_version"],
        search_text="text",
        access_scope=values["access_scope"],
        metadata={},
    )

    with pytest.raises(ValueError, match="command"):
        build_index_inputs(_command(), [chunk], {})
