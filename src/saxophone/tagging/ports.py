"""Application ports for paragraph tagging providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from .models import (
    TagConflictResolution,
    TagConflictResolutionRequest,
    TagGenerationRequest,
    TagGenerationResult,
    TaggedParagraph,
)


class TaggedParagraphRepository(Protocol):
    """Persist source-preserving tag results independently from the vector index."""

    async def upsert(self, paragraph: TaggedParagraph) -> None:
        """Create or replace one tagged paragraph by stable paragraph ID."""

    async def get(self, paragraph_id: str) -> TaggedParagraph:
        """Return a tagged paragraph or raise ``FileNotFoundError``."""

    async def delete(self, paragraph_id: str) -> None:
        """Delete one tagged paragraph or raise ``FileNotFoundError``."""


class TagCatalogRepository(Protocol):
    """Persist the plain-English tag vocabulary separately from paragraph sidecars."""

    async def add(self, tags: tuple[str, ...]) -> None:
        """Add validated tags idempotently to the catalog."""

    async def list(self) -> tuple[str, ...]:
        """Return catalog tags in a deterministic order."""


class TagGenerator(ABC):
    """Async port for remote generation of paragraph topic tags."""

    @abstractmethod
    async def generate(
        self, request: TagGenerationRequest
    ) -> TagGenerationResult:
        raise NotImplementedError


class TagConflictResolver(ABC):
    """Async port for the separate existing-vs-new tag resolution task."""

    @abstractmethod
    async def resolve(
        self, request: TagConflictResolutionRequest
    ) -> TagConflictResolution:
        raise NotImplementedError
