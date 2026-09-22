from __future__ import annotations

import hashlib

import pytest

from saxophone.ingestion.concept_records import build_concept_vector_record
from saxophone.tagging.concepts import ConceptCandidate, ConceptCandidateExample


def _candidate() -> ConceptCandidate:
    return ConceptCandidate(
        canonical_label="Major triad",
        rank=1,
        semantic_score=0.92,
        usage_count=4,
        examples=(
            ConceptCandidateExample(
                header="Major triads",
                excerpt="A major triad consists of a root, a major third, and a perfect fifth.",
            ),
            ConceptCandidateExample(
                header="Building a major triad",
                excerpt="Begin with the root and add the major third.",
            ),
        ),
    )


def test_concept_vector_record_has_stable_identity_and_search_projection() -> None:
    record = build_concept_vector_record(
        _candidate(),
        embedding=(0.1, 0.2, 0.3),
        embedding_model="text-embedding-3-small",
        index_version="concept-v1",
    )

    normalized = "major triad"
    expected_id = "concept::" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    assert record.record_id == expected_id
    assert record.canonical_label == "Major triad"
    assert record.normalized_label == normalized
    assert record.search_text == (
        "Major triad\n"
        "Major triads: A major triad consists of a root, a major third, and a perfect fifth.\n"
        "Building a major triad: Begin with the root and add the major third."
    )
    assert record.embedding_input_hash == hashlib.sha256(
        record.search_text.encode("utf-8")
    ).hexdigest()
    assert record.embedding_dimensions == 3
    assert record.metadata["canonical_label"] == "Major triad"


def test_concept_vector_record_limits_representative_examples_deterministically() -> None:
    candidate = ConceptCandidate(
        canonical_label="Harmony",
        rank=1,
        semantic_score=0.8,
        examples=tuple(
            ConceptCandidateExample(header=f"H{i}", excerpt=f"E{i}")
            for i in range(5)
        ),
    )

    record = build_concept_vector_record(
        candidate,
        embedding=(1.0,),
        embedding_model="fake",
        index_version="v1",
        max_examples=2,
    )

    assert record.search_text == "Harmony\nH0: E0\nH1: E1"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("embedding_model", ""),
        ("index_version", ""),
        ("max_examples", 0),
        ("embedding", ()),
        ("embedding", (1.0, float("nan"))),
    ],
)
def test_concept_vector_record_rejects_invalid_projection_inputs(field: str, value: object) -> None:
    kwargs = {
        "embedding": (0.1, 0.2),
        "embedding_model": "fake",
        "index_version": "v1",
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        build_concept_vector_record(_candidate(), **kwargs)
