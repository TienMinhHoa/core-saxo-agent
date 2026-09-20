from __future__ import annotations

import pytest

from saxophone.retrieval.candidates import InMemoryCandidateSetRepository
from saxophone.retrieval.models import ChunkHit


def _hit(chunk_ref: str) -> ChunkHit:
    return ChunkHit(
        "document-1",
        chunk_ref,
        1,
        "retrieval-v1",
        {"document": "source text"},
        semantic_score=0.8,
    )


def test_candidate_set_round_trips_immutable_hits() -> None:
    repository = InMemoryCandidateSetRepository(clock=lambda: 100.0)

    token = repository.save((_hit("chunk-1"),), ttl_seconds=30.0)

    assert repository.get(token) == (_hit("chunk-1"),)


def test_candidate_set_expires_and_is_removed() -> None:
    now = [100.0]
    repository = InMemoryCandidateSetRepository(clock=lambda: now[0])
    token = repository.save((_hit("chunk-1"),), ttl_seconds=5.0)

    now[0] = 105.0
    with pytest.raises(KeyError, match="expired"):
        repository.get(token)

    assert repository.size == 0


def test_candidate_set_capacity_evicts_oldest_entry() -> None:
    repository = InMemoryCandidateSetRepository(capacity=1, clock=lambda: 100.0)
    first = repository.save((_hit("chunk-1"),), ttl_seconds=30.0)
    second = repository.save((_hit("chunk-2"),), ttl_seconds=30.0)

    with pytest.raises(KeyError, match="unknown"):
        repository.get(first)
    assert repository.get(second) == (_hit("chunk-2"),)


def test_candidate_set_rejects_invalid_ttl_and_empty_hits() -> None:
    repository = InMemoryCandidateSetRepository(clock=lambda: 100.0)

    with pytest.raises(ValueError, match="ttl_seconds"):
        repository.save((_hit("chunk-1"),), ttl_seconds=0)
    with pytest.raises(ValueError, match="hits"):
        repository.save((), ttl_seconds=1)
