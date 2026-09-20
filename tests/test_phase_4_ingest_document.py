from __future__ import annotations

import pytest

from saxophone.ingestion.models import (
    EmbeddingRecord,
    IngestionCommand,
    IngestionSourceChunk,
)
from saxophone.ingestion.use_cases import IngestDocument, IndexDocument
from saxophone.tagging.models import ParagraphBlock, TaggedParagraph


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
        search_text="Source text.",
        access_scope="tenant-a",
        metadata={"heading": "Heading"},
    )


def _paragraph() -> ParagraphBlock:
    return ParagraphBlock(
        paragraph_id="chunk-1:p0000",
        chunk_id="chunk-1",
        ordinal=0,
        text="Source text.",
    )


class FakeTagAndPersist:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, paragraph, *, tagging_profile, resolution_profile):
        self.calls.append((paragraph, tagging_profile, resolution_profile))
        return TaggedParagraph(
            paragraph_id=paragraph.paragraph_id,
            text=paragraph.text,
            generated_tags=("source",),
            tags=("source",),
            status="completed",
        )


class FakeEmbedding:
    async def embed(self, chunks, *, source_version):
        return tuple(
            EmbeddingRecord(
                chunk_id=chunk_id,
                source_version=source_version,
                model_profile="embed-v1",
                vector=(0.1, 0.2),
            )
            for chunk_id, _ in chunks
        )


class FakeIndex:
    async def upsert_chunks(self, records):
        self.records = tuple(records)


@pytest.mark.anyio
async def test_ingest_document_tags_persists_then_indexes_source_projection() -> None:
    tagger = FakeTagAndPersist()
    index = FakeIndex()
    workflow = IngestDocument(tagger, IndexDocument(index, FakeEmbedding()))

    report = await workflow.execute(
        _command(), [_chunk()], [_paragraph()], resolution_profile="resolve-v1"
    )

    assert len(tagger.calls) == 1
    assert tagger.calls[0][1:] == ("tag-v1", "resolve-v1")
    assert index.records[0].search_text == "Source text."
    assert index.records[0].metadata["tags"] == ("source",)
    assert report.indexed is True


@pytest.mark.anyio
async def test_ingest_document_rejects_paragraph_from_unknown_chunk_before_tagging() -> None:
    tagger = FakeTagAndPersist()
    workflow = IngestDocument(tagger, IndexDocument(FakeIndex(), FakeEmbedding()))
    paragraph = ParagraphBlock(
        paragraph_id="missing:p0000",
        chunk_id="missing",
        ordinal=0,
        text="Orphan text.",
    )

    with pytest.raises(ValueError, match="supplied chunk"):
        await workflow.execute(
            _command(), [_chunk()], [paragraph], resolution_profile="resolve-v1"
        )

    assert tagger.calls == []
