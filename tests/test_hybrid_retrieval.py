from __future__ import annotations

import pytest

from music_rag.store import CatalogStore
from saxophone.retrieval.adapters import (
    HybridRetriever,
    InMemoryLexicalRetriever,
    LegacySemanticRetriever,
)
from saxophone.retrieval.models import ChunkHit


def _hit(
    ref: str,
    rank: int,
    *,
    semantic: float | None = None,
    keyword: float | None = None,
) -> ChunkHit:
    return ChunkHit(
        source_ref="document-1",
        chunk_ref=ref,
        rank=rank,
        retrieval_version="retrieval-v1",
        metadata={"document": ref},
        semantic_score=semantic,
        keyword_score=keyword,
    )


class _StaticRetriever:
    def __init__(self, hits: list[ChunkHit]) -> None:
        self.hits = hits

    async def search(self, query: str, *, filters=None, limit: int = 10):
        return self.hits[:limit]


@pytest.mark.anyio
async def test_lexical_retriever_scores_header_content_and_tags() -> None:
    retriever = InMemoryLexicalRetriever(
        [
            _hit("chunk-harmony", 1),
            ChunkHit(
                "document-1",
                "chunk-rhythm",
                2,
                "retrieval-v1",
                {"heading": "Rhythm", "document": "steady pulse", "tags": ["beat"]},
            ),
        ]
    )

    hits = await retriever.search("harmony", limit=10)

    assert [hit.chunk_ref for hit in hits] == ["chunk-harmony"]
    assert hits[0].keyword_score == pytest.approx(1.0)


@pytest.mark.anyio
async def test_hybrid_retriever_fuses_overlapping_results_with_rrf() -> None:
    semantic = _StaticRetriever([_hit("shared", 1, semantic=0.9), _hit("dense", 2)])
    lexical = _StaticRetriever(
        [_hit("shared", 1, keyword=0.8), _hit("lexical", 2, keyword=0.4)]
    )
    retriever = HybridRetriever(semantic, lexical, rrf_k=60)

    hits = await retriever.search("query", limit=3)

    assert [hit.chunk_ref for hit in hits] == ["shared", "dense", "lexical"]
    assert hits[0].fused_score == pytest.approx(2 / 61)
    assert hits[0].semantic_score == pytest.approx(0.9)
    assert hits[0].keyword_score == pytest.approx(0.8)
    assert [hit.rank for hit in hits] == [1, 2, 3]


@pytest.mark.anyio
async def test_hybrid_retriever_rejects_invalid_rrf_k_and_filters_results() -> None:
    with pytest.raises(ValueError, match="rrf_k"):
        HybridRetriever(_StaticRetriever([]), _StaticRetriever([]), rrf_k=0)

    class _Filtered(_StaticRetriever):
        async def search(self, query: str, *, filters=None, limit: int = 10):
            assert filters == {"scope": "public"}
            return await super().search(query, filters=filters, limit=limit)

    retriever = HybridRetriever(_Filtered([_hit("one", 1)]), _Filtered([]))
    assert [hit.chunk_ref for hit in await retriever.search("q", filters={"scope": "public"})] == ["one"]


@pytest.mark.anyio
async def test_legacy_semantic_retriever_maps_legacy_results_to_chunk_hits(tmp_path) -> None:
    class _Provider:
        model = "legacy-test-v1"

        def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    CatalogStore(tmp_path).save(
        {
            "documents": {"doc-1:v1": {"access_scope": "public"}},
            "items": {
                "item-1:1": {
                    "item_id": "item-1",
                    "item_version": 1,
                    "document_id": "doc-1",
                    "source_version": "v1",
                    "review_status": "approved",
                }
            },
            "semantic_index": {
                "provider_model": "legacy-test-v1",
                "units": [
                    {
                        "search_unit_id": "semantic_item-1:1:1",
                        "item_id": "item-1",
                        "item_version": 1,
                        "document_id": "doc-1",
                        "source_version": "v1",
                        "evidence_block_ids": ["block-1"],
                        "evidence_scope": "item",
                        "embedding": [1.0, 0.0],
                        "search_text": "rhythm pulse",
                    }
                ],
            },
        }
    )

    retriever = LegacySemanticRetriever(CatalogStore(tmp_path), _Provider())

    hits = await retriever.search("pulse", filters={"access_scope": "public"})

    assert len(hits) == 1
    assert hits[0].source_ref == "doc-1:v1"
    assert hits[0].chunk_ref == "semantic_item-1:1:1"
    assert hits[0].retrieval_version == "legacy-semantic-v1"
    assert hits[0].metadata["evidence_block_ids"] == ["block-1"]
    assert hits[0].semantic_score == pytest.approx(0.85 + 0.15)
    assert hits[0].keyword_score == pytest.approx(1.0)


@pytest.mark.anyio
async def test_legacy_semantic_retriever_requires_access_scope_filter(tmp_path) -> None:
    retriever = LegacySemanticRetriever(CatalogStore(tmp_path), object())

    with pytest.raises(ValueError, match="access_scope"):
        await retriever.search("pulse")
