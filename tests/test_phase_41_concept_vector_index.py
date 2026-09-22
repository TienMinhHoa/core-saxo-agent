from __future__ import annotations

import pytest

from saxophone.ingestion.adapters import ChromaVectorIndex
from saxophone.ingestion.concept_records import ConceptVectorRecord, build_concept_vector_record
from saxophone.ingestion.ports import ConceptVectorIndex
from saxophone.tagging.concepts import ConceptCandidate, ConceptCandidateExample


class _FakeCollection:
    def __init__(self) -> None:
        self.upsert_call = None
        self.query_call = None
        self.delete_call = None

    def upsert(self, **kwargs):
        self.upsert_call = kwargs

    def query(self, **kwargs):
        self.query_call = kwargs
        record = _record()
        return {
            "ids": [[record.record_id]],
            "documents": [[record.search_text]],
            "metadatas": [[dict(record.metadata)]],
            "distances": [[0.14]],
        }

    def delete(self, **kwargs):
        self.delete_call = kwargs


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
    assert hasattr(ConceptVectorIndex, "query_concepts")
    assert hasattr(ConceptVectorIndex, "delete_concepts")


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


@pytest.mark.anyio
async def test_chroma_queries_the_separate_concept_catalog_and_returns_typed_hits() -> None:
    chunk_collection = _FakeCollection()
    concept_collection = _FakeCollection()
    index = ChromaVectorIndex(
        chunk_collection,
        concept_collection=concept_collection,
        embedding_dimension=2,
    )

    hits = await index.query_concepts((0.4, 0.5), limit=3)

    assert chunk_collection.query_call is None
    assert concept_collection.query_call == {
        "query_embeddings": [[0.4, 0.5]],
        "n_results": 3,
        "include": ["documents", "metadatas", "distances"],
    }
    assert len(hits) == 1
    assert hits[0].record_id == _record().record_id
    assert hits[0].canonical_label == "Major triad"
    assert hits[0].normalized_label == "major triad"
    assert hits[0].search_text == _record().search_text
    assert hits[0].distance == 0.14


@pytest.mark.anyio
async def test_chroma_deletes_concepts_only_from_the_catalog_collection() -> None:
    chunk_collection = _FakeCollection()
    concept_collection = _FakeCollection()
    index = ChromaVectorIndex(
        chunk_collection,
        concept_collection=concept_collection,
    )

    await index.delete_concepts([_record().record_id])

    assert chunk_collection.delete_call is None
    assert concept_collection.delete_call == {"ids": [_record().record_id]}


@pytest.mark.anyio
async def test_chroma_concept_delete_rejects_duplicate_or_foreign_ids_before_provider_io() -> None:
    concept_collection = _FakeCollection()
    index = ChromaVectorIndex(object(), concept_collection=concept_collection)
    record_id = _record().record_id

    with pytest.raises(ValueError, match="unique"):
        await index.delete_concepts([record_id, record_id])
    with pytest.raises(ValueError, match="concept record IDs"):
        await index.delete_concepts(["chunk-1"])

    assert concept_collection.delete_call is None


@pytest.mark.anyio
async def test_chroma_concept_query_rejects_malformed_catalog_metadata() -> None:
    class _MalformedCollection(_FakeCollection):
        def query(self, **kwargs):
            self.query_call = kwargs
            record = _record()
            metadata = dict(record.metadata)
            metadata["normalized_label"] = "different"
            return {
                "ids": [[record.record_id]],
                "documents": [[record.search_text]],
                "metadatas": [[metadata]],
                "distances": [[0.14]],
            }

    collection = _MalformedCollection()
    index = ChromaVectorIndex(
        object(),
        concept_collection=collection,
        embedding_dimension=2,
    )

    with pytest.raises(ValueError, match="normalized_label"):
        await index.query_concepts((0.4, 0.5))
