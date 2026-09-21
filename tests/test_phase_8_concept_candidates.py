from __future__ import annotations

import pytest

from saxophone.tagging.concepts import (
    ConceptCandidate,
    ConceptCandidateExample,
    deduplicate_concept_candidates,
    normalize_concept_label,
)


def test_concept_normalization_collapses_spacing_unicode_and_case() -> None:
    assert normalize_concept_label("  Mélodie\u00a0  HARMONIQUE ") == "mélodie harmonique"


def test_candidate_derives_and_validates_normalized_label() -> None:
    candidate = ConceptCandidate("  Major   Triad ", 1, 0.842, examples=(
        ConceptCandidateExample("Triads", "A major triad contains..."),
    ))
    assert candidate.canonical_label == "Major Triad"
    assert candidate.normalized_label == "major triad"
    with pytest.raises(ValueError, match="normalized_label"):
        ConceptCandidate("Major triad", 1, 0.8, normalized_label="wrong")
    with pytest.raises(ValueError, match="semantic_score"):
        ConceptCandidate("Major triad", 1, float("nan"))


def test_candidates_deduplicate_by_normalized_canonical_label() -> None:
    candidates = deduplicate_concept_candidates((
        ConceptCandidate("Harmony", 2, 0.9),
        ConceptCandidate(" harmony ", 1, 0.7),
        ConceptCandidate("Harmonics", 3, 0.8),
    ))
    assert [(item.canonical_label, item.rank) for item in candidates] == [
        ("harmony", 1),
        ("Harmonics", 3),
    ]


def test_empty_candidate_catalog_is_deterministically_empty() -> None:
    assert deduplicate_concept_candidates(()) == ()
