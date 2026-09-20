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


def test_chunk_hit_rejects_boolean_rank_and_scores() -> None:
    with pytest.raises(ValueError, match="rank"):
        ChunkHit("document-1", "chunk-1", True, "retrieval-v1", {})  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="semantic_score"):
        ChunkHit("document-1", "chunk-1", 1, "retrieval-v1", {}, semantic_score=True)  # type: ignore[arg-type]


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


@pytest.mark.parametrize("field_name", ["query", "retrieval_version"])
@pytest.mark.parametrize("value", [" value", "value ", "cafe\u0301"])
def test_evidence_bundle_rejects_non_canonical_identity_fields(
    field_name: str, value: str
) -> None:
    values: dict[str, object] = {
        "query": "what is this?",
        "retrieval_version": "retrieval-v1",
    }
    values[field_name] = value

    with pytest.raises(ValueError, match="canonical"):
        EvidenceBundle(
            values["query"],  # type: ignore[arg-type]
            values["retrieval_version"],  # type: ignore[arg-type]
            (_hit(),),
            ("chunk-1",),
            {"chunk-1": "text"},
        )


def test_evidence_bundle_requires_retrieval_version_to_match_all_hits() -> None:
    with pytest.raises(ValueError, match="retrieval_version"):
        EvidenceBundle(
            "what is this?",
            "retrieval-v2",
            (_hit(),),
            ("chunk-1",),
            {"chunk-1": "text"},
        )


def test_empty_evidence_requires_explicit_insufficiency_reason() -> None:
    with pytest.raises(ValueError, match="insufficiency_reason"):
        EvidenceBundle("query", "retrieval-v1", (), (), {})

    bundle = EvidenceBundle(
        "query", "retrieval-v1", (), (), {}, insufficiency_reason="no matching source"
    )
    assert bundle.insufficiency_reason == "no matching source"


@pytest.mark.parametrize("reason", ["", " ", "no source ", "cafe\u0301"])
def test_evidence_bundle_rejects_non_canonical_insufficiency_reason(reason: str) -> None:
    with pytest.raises(ValueError, match="insufficiency_reason"):
        EvidenceBundle("query", "retrieval-v1", (), (), {}, insufficiency_reason=reason)


@pytest.mark.parametrize("reason", [True, 0, object()])
def test_evidence_bundle_rejects_non_string_insufficiency_reason(reason: object) -> None:
    with pytest.raises(ValueError, match="insufficiency_reason"):
        EvidenceBundle(  # type: ignore[arg-type]
            "query", "retrieval-v1", (), (), {}, insufficiency_reason=reason
        )


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


@pytest.mark.parametrize("field_name", ["selected_refs", "image_refs"])
def test_evidence_bundle_rejects_string_refs_instead_of_tuples(field_name: str) -> None:
    values: dict[str, object] = {
        "selected_refs": ("chunk-1",),
        "image_refs": (),
    }
    values[field_name] = "chunk-1"

    with pytest.raises(ValueError, match=field_name):
        EvidenceBundle(
            "query",
            "retrieval-v1",
            (_hit(),),
            values["selected_refs"],  # type: ignore[arg-type]
            {"chunk-1": "text"},
            values["image_refs"],  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("field_name", ["source_ref", "chunk_ref", "retrieval_version"])
@pytest.mark.parametrize("value", [" value", "value ", "cafe\u0301"])
def test_chunk_hit_rejects_non_canonical_identity_fields(field_name: str, value: str) -> None:
    values: dict[str, object] = {
        "source_ref": "document-1",
        "chunk_ref": "chunk-1",
        "retrieval_version": "retrieval-v1",
    }
    values[field_name] = value

    with pytest.raises(ValueError, match="canonical"):
        ChunkHit(
            values["source_ref"],  # type: ignore[arg-type]
            values["chunk_ref"],  # type: ignore[arg-type]
            1,
            values["retrieval_version"],  # type: ignore[arg-type]
            {"document": "text"},
        )
