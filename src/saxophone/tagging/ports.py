"""Application ports for paragraph tagging providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import (
    TagConflictResolution,
    TagConflictResolutionRequest,
    TagGenerationRequest,
    TagGenerationResult,
)


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
