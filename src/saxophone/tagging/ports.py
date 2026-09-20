"""Application ports for paragraph tagging providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import TagGenerationRequest, TagGenerationResult


class TagGenerator(ABC):
    """Async port for remote generation of paragraph topic tags."""

    @abstractmethod
    async def generate(
        self, request: TagGenerationRequest
    ) -> TagGenerationResult:
        raise NotImplementedError
