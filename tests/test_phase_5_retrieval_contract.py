from __future__ import annotations

import math

import pytest

from saxophone.retrieval.models import ChunkHit, EvidenceBundle
from saxophone.retrieval.ports import ChunkRetriever


def _hit() -> ChunkHit:
    return ChunkHit(
        source_ref="document-1",
        chunk_ref="chunk-1",
        rank=1,
        retrieval_version="retrieval-v1",
        metadata={"page_start": 2, "heading": "Overview"},
        semantic_score=0.91,
        fused_score=0.91,
    )


def test_chunk_hit_exposes_provider_independent_rank_and_scores() -> None:
    hit = _hit()

    assert hit.chunk_ref == "chunk-1"
    assert hit.rank == 1
    assert hit.metadata["heading"] == "Overview"


def test_chunk_hit_rejects_invalid_rank_and_non_finite_score() -> None:
    with pytest.raises(ValueError, match="rank"):
        ChunkHit("document-1", "chunk-1", 0, "retrieval-v1", {})
    with pytest.raises(ValueError, match="finite"):
        ChunkHit("document-1", "chunk-1", 1, "retrieval-v1", {}, fused_score=math.inf)


def test_evidence_bundle_validates_source_text_and_keeps_mapping_immutable() -> None:
    source_texts = {"chunk-1": "Validated source text"}
    bundle = EvidenceBundle(
        query="what is this?",
        retrieval_version="retrieval-v1",
        hits=(_hit(),),
        selected_refs=("chunk-1",),
        source_texts=source_texts,
        image_refs=("image-1",),
    )

    source_texts["chunk-2"] = "outside mutation"
    assert bundle.source_texts == {"chunk-1": "Validated source text"}
    with pytest.raises(TypeError):
        bundle.source_texts["chunk-1"] = "mutation"  # type: ignore[index]


def test_empty_evidence_requires_explicit_insufficiency_reason() -> None:
    with pytest.raises(ValueError, match="insufficiency_reason"):
        EvidenceBundle("query", "retrieval-v1", (), (), {})

    bundle = EvidenceBundle(
        "query", "retrieval-v1", (), (), {}, insufficiency_reason="no matching source"
    )
    assert bundle.insufficiency_reason == "no matching source"


def test_evidence_bundle_rejects_insufficiency_with_hits() -> None:
    with pytest.raises(ValueError, match="empty evidence"):
        EvidenceBundle(
            "query", "retrieval-v1", (_hit(),), ("chunk-1",), {"chunk-1": "text"},
            insufficiency_reason="ambiguous",
        )


def test_evidence_bundle_requires_selected_refs_to_match_hits_and_source_texts() -> None:
    with pytest.raises(ValueError, match="selected_refs"):
        EvidenceBundle(
            "query",
            "retrieval-v1",
            (_hit(),),
            ("unknown-chunk",),
            {"unknown-chunk": "text"},
        )

    with pytest.raises(ValueError, match="source_texts"):
        EvidenceBundle(
            "query",
            "retrieval-v1",
            (_hit(),),
            ("chunk-1",),
            {},
        )


def test_chunk_retriever_is_async_application_port() -> None:
    assert hasattr(ChunkRetriever, "search")
