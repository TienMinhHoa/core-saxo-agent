"""Application port for task-specific answer generation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from saxophone.retrieval.models import EvidenceBundle

from .models import GeneratedAnswer


class ImageArtifactGate(ABC):
    """Validate image references before they reach an answer provider."""

    @abstractmethod
    async def validate(self, image_refs: tuple[str, ...]) -> tuple[str, ...]:
        raise NotImplementedError


class AnswerGenerator(ABC):
    """Generate an answer from validated evidence only."""

    @abstractmethod
    async def generate(self, question: str, evidence: EvidenceBundle) -> GeneratedAnswer:
        raise NotImplementedError
