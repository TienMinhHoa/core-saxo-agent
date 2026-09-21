"""Canonical concept labels and deterministic candidate projections."""

from __future__ import annotations

import unicodedata
import math
from dataclasses import dataclass
from collections.abc import Iterable, Sequence


def normalize_concept_label(label: str) -> str:
    """Return the stable lookup key used for concepts and aliases."""
    if not isinstance(label, str) or not label.strip():
        raise ValueError("concept label must not be blank")
    normalized = " ".join(unicodedata.normalize("NFC", label).split())
    return normalized.casefold()


@dataclass(frozen=True, slots=True)
class ConceptCandidateExample:
    header: str
    excerpt: str

    def __post_init__(self) -> None:
        for name in ("header", "excerpt"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be blank")
            object.__setattr__(self, name, value.strip())


@dataclass(frozen=True, slots=True)
class ConceptCandidate:
    canonical_label: str
    rank: int
    semantic_score: float
    usage_count: int = 0
    examples: tuple[ConceptCandidateExample, ...] = ()
    normalized_label: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_label, str) or not self.canonical_label.strip():
            raise ValueError("canonical_label must not be blank")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError("rank must be a positive integer")
        if (
            isinstance(self.semantic_score, bool)
            or not isinstance(self.semantic_score, (int, float))
            or not math.isfinite(self.semantic_score)
        ):
            raise ValueError("semantic_score must be numeric")
        if isinstance(self.usage_count, bool) or not isinstance(self.usage_count, int) or self.usage_count < 0:
            raise ValueError("usage_count must be a non-negative integer")
        if any(not isinstance(example, ConceptCandidateExample) for example in self.examples):
            raise ValueError("examples must contain ConceptCandidateExample values")
        canonical = " ".join(unicodedata.normalize("NFC", self.canonical_label).split())
        normalized = normalize_concept_label(canonical)
        if self.normalized_label and self.normalized_label != normalized:
            raise ValueError("normalized_label does not match canonical_label")
        object.__setattr__(self, "canonical_label", canonical)
        object.__setattr__(self, "normalized_label", normalized)
        object.__setattr__(self, "examples", tuple(self.examples))


def rank_concept_candidates(
    query_text: str,
    candidates: Sequence[ConceptCandidate],
    *,
    limit: int,
) -> tuple[ConceptCandidate, ...]:
    """Rank candidates deterministically, preferring exact normalized matches.

    This is an application-level projection: production vector search can supply
    the candidates, while exact lookup and final ordering remain consistent.
    """
    if not isinstance(query_text, str) or not query_text.strip():
        raise ValueError("query_text must not be blank")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    unique = deduplicate_concept_candidates(candidates)
    query_key = normalize_concept_label(query_text)
    query_tokens = set(query_key.split())

    def sort_key(candidate: ConceptCandidate) -> tuple[int, float, int, str]:
        candidate_key = candidate.normalized_label
        exact = 0 if candidate_key == query_key else 1
        overlap = len(query_tokens & set(candidate_key.split()))
        return (exact, -overlap, candidate.rank, candidate_key)

    return tuple(sorted(unique, key=sort_key)[:limit])


def deduplicate_concept_candidates(
    candidates: Iterable[ConceptCandidate],
) -> tuple[ConceptCandidate, ...]:
    """Keep the best-ranked candidate for each canonical concept key."""
    best: dict[str, ConceptCandidate] = {}
    for candidate in candidates:
        if not isinstance(candidate, ConceptCandidate):
            raise ValueError("candidates must contain ConceptCandidate values")
        current = best.get(candidate.normalized_label)
        if current is None or (candidate.rank, -candidate.semantic_score) < (
            current.rank,
            -current.semantic_score,
        ):
            best[candidate.normalized_label] = candidate
    return tuple(sorted(best.values(), key=lambda item: (item.rank, item.normalized_label)))
