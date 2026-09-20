"""Application port for task-specific answer generation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from saxophone.retrieval.models import EvidenceBundle

from .models import GeneratedAnswer


class AnswerGenerator(ABC):
    """Generate an answer from validated evidence only."""

    @abstractmethod
    async def generate(self, question: str, evidence: EvidenceBundle) -> GeneratedAnswer:
        raise NotImplementedError
