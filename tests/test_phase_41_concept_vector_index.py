from __future__ import annotations

import pytest

from saxophone.ingestion.adapters import ChromaVectorIndex
from saxophone.ingestion.concept_records import ConceptVectorRecord, build_concept_vector_record
from saxophone.ingestion.ports import ConceptVectorIndex
from saxophone.tagging.concepts import ConceptCandidate, ConceptCandidateExample


class _FakeCollection:
    def __init__(self) -> None:
        self.upsert_call = None

    def upsert(self, **kwargs):
        self.upsert_call = kwargs


def _record(*, embedding: tuple[float, ...] = (0.1, 0.2)) -> ConceptVectorRecord:
    candidate = ConceptCandidate(
        canonical_label="Major triad",
        rank=1,
        semantic_score=0.9,
        usage_count=3,
        examples=(
            ConceptCandidateExample(
                header="Triads",
                excerpt="A major triad contains a root, third, and fifth.",
            ),
        ),
    )
    return build_concept_vector_record(
        candidate,
        embedding=embedding,
        embedding_model="text-embedding-3-small",
        index_version="concept-v1",
    )


def test_concept_vector_index_is_an_async_port() -> None:
    assert hasattr(ConceptVectorIndex, "upsert_concepts")


@pytest.mark.anyio
async def test_chroma_upserts_concepts_into_the_separate_catalog_collection() -> None:
    chunk_collection = _FakeCollection()
    concept_collection = _FakeCollection()
    index = ChromaVectorIndex(
        chunk_collection,
        concept_collection=concept_collection,
    )

    await index.upsert_concepts([_record()])

    assert chunk_collection.upsert_call is None
    assert concept_collection.upsert_call["ids"] == [_record().record_id]
    assert concept_collection.upsert_call["documents"] == [
        "Major triad\nTriads: A major triad contains a root, third, and fifth."
    ]
    assert concept_collection.upsert_call["metadatas"] == [
        {
            "canonical_label": "Major triad",
            "normalized_label": "major triad",
            "usage_count": 3,
            "embedding_input_hash": _record().embedding_input_hash,
            "embedding_model": "text-embedding-3-small",
            "embedding_dimensions": 2,
            "index_version": "concept-v1",
        }
    ]


@pytest.mark.anyio
async def test_chroma_concept_upsert_requires_a_catalog_collection() -> None:
    class _CollectionThatMustNotBeCalled:
        def upsert(self, **kwargs):
            raise AssertionError("missing concept collection reached Chroma")

    index = ChromaVectorIndex(_CollectionThatMustNotBeCalled())

    with pytest.raises(ValueError, match="concept_collection"):
        await index.upsert_concepts([_record()])


@pytest.mark.anyio
async def test_chroma_concept_upsert_rejects_duplicate_ids_before_provider_io() -> None:
    class _CollectionThatMustNotBeCalled:
        def upsert(self, **kwargs):
            raise AssertionError("duplicate concept IDs reached Chroma")

    index = ChromaVectorIndex(
        object(),
        concept_collection=_CollectionThatMustNotBeCalled(),
    )
    record = _record()

    with pytest.raises(ValueError, match="unique"):
        await index.upsert_concepts([record, record])


@pytest.mark.anyio
async def test_chroma_concept_upsert_rejects_mixed_dimensions_before_provider_io() -> None:
    class _CollectionThatMustNotBeCalled:
        def upsert(self, **kwargs):
            raise AssertionError("mixed dimensions reached Chroma")

    index = ChromaVectorIndex(
        object(),
        concept_collection=_CollectionThatMustNotBeCalled(),
    )
    first = _record()
    second_candidate = ConceptCandidate(
        canonical_label="Minor triad",
        rank=2,
        semantic_score=0.8,
        examples=(ConceptCandidateExample(header="Triads", excerpt="A minor triad."),),
    )
    second = build_concept_vector_record(
        second_candidate,
        embedding=(0.3,),
        embedding_model="text-embedding-3-small",
        index_version="concept-v1",
    )

    with pytest.raises(ValueError, match="shared dimension"):
        await index.upsert_concepts([first, second])

