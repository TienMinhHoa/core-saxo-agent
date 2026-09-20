"""Bounded in-memory storage for retrieval candidate sets."""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Callable, Sequence
from time import monotonic
from uuid import uuid4

from .models import ChunkHit


class InMemoryCandidateSetRepository:
    """Store candidate hits with bounded capacity and monotonic TTL expiry."""

    def __init__(
        self,
        *,
        capacity: int = 256,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self._capacity = capacity
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, tuple[ChunkHit, ...]]] = (
            OrderedDict()
        )
        self._expired: deque[str] = deque(maxlen=capacity)

    @property
    def size(self) -> int:
        self._purge_expired()
        return len(self._entries)

    def save(self, hits: Sequence[ChunkHit], *, ttl_seconds: float) -> str:
        if not hits:
            raise ValueError("hits must not be empty")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        candidate_hits = tuple(hits)
        if any(not isinstance(hit, ChunkHit) for hit in candidate_hits):
            raise ValueError("hits must contain ChunkHit values")

        self._purge_expired()
        token = uuid4().hex
        self._entries[token] = (self._clock() + ttl_seconds, candidate_hits)
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)
        return token

    def get(self, token: str) -> tuple[ChunkHit, ...]:
        self._purge_expired()
        entry = self._entries.get(token)
        if entry is None:
            if token in self._expired:
                raise KeyError(f"expired candidate set: {token}")
            raise KeyError(f"unknown candidate set: {token}")
        return entry[1]

    def delete(self, token: str) -> None:
        self._entries.pop(token, None)

    def _purge_expired(self) -> None:
        now = self._clock()
        expired = [token for token, (deadline, _) in self._entries.items() if deadline <= now]
        for token in expired:
            del self._entries[token]
            self._expired.append(token)
