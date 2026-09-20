"""Chat application use case, independent from model and retrieval SDKs."""

from __future__ import annotations

from collections.abc import Mapping

from saxophone.retrieval.models import EvidenceBundle
from saxophone.retrieval.use_cases import RetrieveEvidence

from .models import ChatResult, ChatStatus, evidence_reference
from .ports import AnswerGenerator


class AnswerQuestion:
    """Retrieve validated evidence, then delegate grounded synthesis."""

    def __init__(
        self,
        retrieve_evidence: RetrieveEvidence,
        answer_generator: AnswerGenerator,
    ) -> None:
        self._retrieve_evidence = retrieve_evidence
        self._answer_generator = answer_generator

    async def execute(
        self,
        question: str,
        *,
        filters: Mapping[str, object] | None = None,
        limit: int = 10,
    ) -> ChatResult:
        normalized_question = question.strip() if isinstance(question, str) else question
        evidence = await self._retrieve_evidence.execute(
            normalized_question, filters=filters, limit=limit
        )
        if not evidence.hits:
            return ChatResult(
                ChatStatus.INSUFFICIENT_EVIDENCE,
                None,
                (),
                None,
                None,
                {},
                0.0,
            )

        generated = await self._answer_generator.generate(normalized_question, evidence)
        citations = tuple(dict.fromkeys(hit.source_ref for hit in evidence.hits))
        return ChatResult(
            ChatStatus.ANSWERED,
            generated.answer,
            citations,
            evidence_reference(evidence.retrieval_version, evidence.selected_refs),
            generated.model_version,
            generated.token_usage,
            generated.cost,
        )
