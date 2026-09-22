from __future__ import annotations

import pytest

from saxophone.ingestion.models import IngestionSourceChunk
from saxophone.ingestion.transaction import SqliteIngestionTransactionRepository
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.sqlite_context import SqliteRetrievalContextRepository
from saxophone.tagging.models import ContentRole, ParagraphBlock, ParagraphConceptRole


def _chunk() -> IngestionSourceChunk:
    return IngestionSourceChunk(
        chunk_id="chunk-01",
        document_ref="music-book",
        source_version="source-v1",
        search_text="# Major triads\n\nA major triad has a root, third, and fifth.",
        access_scope="tenant-a",
        metadata={
            "source": "music-theory.md",
            "header": "Major and Minor Triads",
            "page_start": 121,
            "page_end": 122,
        },
    )


def _paragraph() -> ParagraphBlock:
    return ParagraphBlock(
        paragraph_id="music-book:chunk-01:abc:1",
        chunk_id="chunk-01",
        ordinal=0,
        text="A major triad has a root, third, and fifth.",
        heading_path=("Major triads",),
        image_refs=("figure-121-01",),
    )


@pytest.mark.anyio
async def test_document_transaction_persists_hydratable_retrieval_context(
    tmp_path,
) -> None:
    database = tmp_path / "ingestion.sqlite3"
    chunk = _chunk()
    paragraph = _paragraph()
    relation = ParagraphConceptRole(
        paragraph.paragraph_id,
        "Major triad",
        ContentRole.DEFINITION,
    )

    await SqliteIngestionTransactionRepository(database).commit_document(
        document_ref=chunk.document_ref,
        source_version=chunk.source_version,
        paragraph_ids=(paragraph.paragraph_id,),
        relations=(relation,),
        outbox_events=(),
        chunks=(chunk,),
        paragraphs=(paragraph,),
    )

    hit = ChunkHit(
        "music-theory.md",
        chunk.chunk_id,
        1,
        "retrieval-v1",
        {
            "document_ref": chunk.document_ref,
            "source_version": chunk.source_version,
            "document": chunk.search_text,
        },
        semantic_score=0.9,
    )
    context = await SqliteRetrievalContextRepository(database).load_for_hits((hit,))

    assert context.relations == (relation,)
    source = context.paragraphs[paragraph.paragraph_id]
    assert source.chunk_id == chunk.chunk_id
    assert source.source == "music-theory.md"
    assert source.parent_header == "Major and Minor Triads"
    assert source.nested_headings == ("Major triads",)
    assert source.pages == ("121", "122")
    assert source.image_refs == ("figure-121-01",)
    assert source.concepts_and_roles == ("Major triad -> Definition",)


@pytest.mark.anyio
async def test_retrieval_context_rejects_hit_without_sqlite_scope(tmp_path) -> None:
    repository = SqliteRetrievalContextRepository(tmp_path / "ingestion.sqlite3")
    hit = ChunkHit(
        "music.md",
        "chunk-01",
        1,
        "retrieval-v1",
        {"document": "text"},
    )

    with pytest.raises(ValueError, match="document_ref"):
        await repository.load_for_hits((hit,))
