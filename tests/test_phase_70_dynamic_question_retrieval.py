from __future__ import annotations

import pytest

from saxophone.ingestion.models import VectorHit
from saxophone.retrieval.adapters import VectorIndexChunkRetriever
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.question_retrieval import (
    QuestionRequest,
    QuestionRetrievalService,
    RetrievalBundleStatus,
)
from saxophone.retrieval.renderers import SourceParagraph
from saxophone.retrieval.role_selection import (
    ConceptRoleSelection,
    ConceptRoleSelectionResult,
)
from saxophone.retrieval.sqlite_context import RetrievalContext
from saxophone.tagging.models import ContentRole, ParagraphConceptRole


class _EmbeddingProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def embed_texts(self, texts):
        self.calls.append(tuple(texts))
        return ((0.25, 0.75),)


class _VectorIndex:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[float, ...], object, int]] = []

    async def search(self, query_vector, *, filters=None, limit: int = 10):
        self.calls.append((tuple(query_vector), filters, limit))
        return [
            VectorHit(
                chunk_id="chunk-01",
                document="A major triad has a root, third, and fifth.",
                metadata={
                    "document_ref": "music-book",
                    "source_version": "source-v1",
                    "source": "music-theory.md",
                },
                distance=0.1,
            )
        ]


@pytest.mark.anyio
async def test_vector_index_retriever_embeds_query_and_maps_ranked_hits() -> None:
    embeddings = _EmbeddingProvider()
    index = _VectorIndex()
    retriever = VectorIndexChunkRetriever(embeddings, index, retrieval_version="topic-v1")

    hits = await retriever.search(
        "  What is a major triad?  ",
        filters={"document_ref": "music-book"},
        limit=3,
    )

    assert embeddings.calls == [("What is a major triad?",)]
    assert index.calls == [((0.25, 0.75), {"document_ref": "music-book"}, 3)]
    assert hits == [
        ChunkHit(
            "music-theory.md",
            "chunk-01",
            1,
            "topic-v1",
            {
                "document_ref": "music-book",
                "source_version": "source-v1",
                "source": "music-theory.md",
                "document": "A major triad has a root, third, and fifth.",
            },
            semantic_score=0.9,
        )
    ]


class _Retriever:
    async def search(self, query: str, *, filters=None, limit: int = 10):
        return [
            ChunkHit(
                "music-theory.md",
                "chunk-01",
                1,
                "topic-v1",
                {"document_ref": "music-book", "source_version": "source-v1"},
                semantic_score=0.9,
            )
        ]


class _ContextRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[ChunkHit, ...]] = []

    async def load_for_hits(self, hits):
        normalized = tuple(hits)
        self.calls.append(normalized)
        relation = ParagraphConceptRole("paragraph-1", "Major triad", ContentRole.DEFINITION)
        paragraph = SourceParagraph(
            "paragraph-1",
            "music-theory.md",
            "Major triads",
            (),
            "A major triad has a root, third, and fifth.",
            ("Major triad -> Definition",),
            ("121",),
            (),
            "chunk-01",
        )
        return RetrievalContext((relation,), {paragraph.paragraph_ref: paragraph})


class _Selector:
    async def select(self, request):
        return ConceptRoleSelectionResult(
            (ConceptRoleSelection("Major triad", (ContentRole.DEFINITION,), 1),)
        )


@pytest.mark.anyio
async def test_question_retrieval_hydrates_context_for_current_hits() -> None:
    context_repository = _ContextRepository()
    service = QuestionRetrievalService(
        retriever=_Retriever(),
        selector=_Selector(),
        context_repository=context_repository,
    )

    result = await service.retrieve(QuestionRequest("What is a major triad?"))

    assert result.status is RetrievalBundleStatus.READY
    assert len(context_repository.calls) == 1
    assert result.answer_context is not None
    assert tuple(item.paragraph_ref for item in result.answer_context.paragraphs) == (
        "paragraph-1",
    )
    assert result.answer_context_markdown is not None
    assert "### [1]" in result.answer_context_markdown
