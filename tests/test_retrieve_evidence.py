from __future__ import annotations

import pytest

from saxophone.retrieval.models import ChunkHit, EvidenceBundle
from saxophone.retrieval.use_cases import RetrieveEvidence


class _Retriever:
    def __init__(self, hits: list[ChunkHit]) -> None:
        self.hits = hits
        self.calls: list[tuple[str, dict[str, object] | None, int]] = []

    async def search(
        self,
        query: str,
        *,
        filters: dict[str, object] | None = None,
        limit: int = 10,
    ) -> list[ChunkHit]:
        self.calls.append((query, filters, limit))
        return self.hits


def _hit(
    chunk_ref: str,
    *,
    version: str = "retrieval-v1",
    document: str = "source text",
    image_refs: list[str] | None = None,
) -> ChunkHit:
    metadata: dict[str, object] = {"document": document, "page_start": 2}
    if image_refs is not None:
        metadata["image_refs"] = image_refs
    return ChunkHit("document-1", chunk_ref, 1, version, metadata, semantic_score=0.8)


@pytest.mark.anyio
async def test_retrieve_evidence_builds_validated_bundle_and_forwards_query() -> None:
    retriever = _Retriever(
        [_hit("chunk-1", image_refs=["image-1"]), _hit("chunk-2", document="second")]
    )

    bundle = await RetrieveEvidence(retriever).execute(
        "  find scales  ", filters={"scope": "public"}, limit=2
    )

    assert bundle.query == "find scales"
    assert bundle.selected_refs == ("chunk-1", "chunk-2")
    assert bundle.source_texts == {"chunk-1": "source text", "chunk-2": "second"}
    assert bundle.image_refs == ("image-1",)
    assert retriever.calls == [("find scales", {"scope": "public"}, 2)]


@pytest.mark.anyio
async def test_retrieve_evidence_returns_explicit_insufficiency_for_no_hits() -> None:
    bundle = await RetrieveEvidence(_Retriever([])).execute("unknown")

    assert bundle.hits == ()
    assert bundle.insufficiency_reason == "no matching evidence"


@pytest.mark.anyio
async def test_retrieve_evidence_rejects_hit_without_validated_source_text() -> None:
    retriever = _Retriever([_hit("chunk-1", document="")])

    with pytest.raises(ValueError, match="source text"):
        await RetrieveEvidence(retriever).execute("find scales")


@pytest.mark.anyio
async def test_retrieve_evidence_rejects_mixed_retrieval_versions() -> None:
    retriever = _Retriever([_hit("chunk-1"), _hit("chunk-2", version="retrieval-v2")])

    with pytest.raises(ValueError, match="retrieval version"):
        await RetrieveEvidence(retriever).execute("find scales")


def test_evidence_bundle_rejects_source_text_not_selected_or_backed_by_a_hit() -> None:
    hit = _hit("chunk-1")

    with pytest.raises(ValueError, match="source_texts must match selected_refs"):
        EvidenceBundle(
            "find scales",
            "retrieval-v1",
            (hit,),
            ("chunk-1",),
            {"chunk-1": "source text", "unselected": "must not cross boundary"},
        )


@pytest.mark.parametrize(
    "hits",
    [
        [_hit("chunk-1")],
        ("not-a-chunk-hit",),
    ],
)
def test_evidence_bundle_rejects_non_tuple_or_invalid_hits(
    hits: object,
) -> None:
    with pytest.raises(ValueError, match="hits"):
        EvidenceBundle(
            "find scales",
            "retrieval-v1",
            hits,  # type: ignore[arg-type]
            ("chunk-1",),
            {"chunk-1": "source text"},
        )


@pytest.mark.parametrize(
    "image_refs",
    [
        (" images/page-1.png",),
        ("images/page-1.png ",),
        ("cafe\u0301.png",),
        ("../secret.png",),
        ("/absolute.png",),
        ("https://example.test/image.png",),
        ("images\\page-1.png",),
        ("images/page-1.png\x00",),
        ("images/page-1.png", "images/page-1.png"),
    ],
)
def test_evidence_bundle_rejects_non_canonical_or_duplicate_image_refs(
    image_refs: tuple[str, ...],
) -> None:
    hit = _hit("chunk-1")

    with pytest.raises(ValueError, match="canonical|safe relative|unsafe image|unique"):
        EvidenceBundle(
            "find scales",
            "retrieval-v1",
            (hit,),
            ("chunk-1",),
            {"chunk-1": "source text"},
            image_refs=image_refs,
        )
