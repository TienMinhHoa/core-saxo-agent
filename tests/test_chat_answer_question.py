from __future__ import annotations

import pytest

from saxophone.chat.models import ChatStatus, GeneratedAnswer
from saxophone.chat.service import AnswerQuestion
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.use_cases import RetrieveEvidence


class _Retriever:
    def __init__(self, hits: list[ChunkHit]) -> None:
        self.hits = hits

    async def search(self, query: str, *, filters=None, limit: int = 10):
        return self.hits


class _AnswerGenerator:
    def __init__(self) -> None:
        self.calls = []

    async def generate(self, question: str, evidence):
        self.calls.append((question, evidence))
        return GeneratedAnswer(
            answer="Use long tones first.",
            model_version="answer-model-v1",
            token_usage={"prompt": 12, "completion": 6, "total": 18},
            cost=0.001,
        )


def _hit() -> ChunkHit:
    return ChunkHit(
        "book-1",
        "chunk-1",
        1,
        "retrieval-v1",
        {"document": "Long tones build stable intonation."},
        semantic_score=0.9,
    )


@pytest.mark.anyio
async def test_answer_question_generates_grounded_result_and_citations() -> None:
    generator = _AnswerGenerator()
    result = await AnswerQuestion(
        RetrieveEvidence(_Retriever([_hit()])), generator
    ).execute("  How should I practice? ")

    assert result.status is ChatStatus.ANSWERED
    assert result.answer == "Use long tones first."
    assert result.citations == ("book-1",)
    assert result.evidence_bundle_ref.startswith("evidence://retrieval-v1/")
    assert result.model_version == "answer-model-v1"
    assert result.token_usage == {"prompt": 12, "completion": 6, "total": 18}
    assert result.cost == 0.001
    assert generator.calls[0][0] == "How should I practice?"


@pytest.mark.anyio
async def test_answer_question_returns_explicit_insufficiency_without_llm_call() -> None:
    generator = _AnswerGenerator()
    result = await AnswerQuestion(RetrieveEvidence(_Retriever([])), generator).execute(
        "unknown"
    )

    assert result.status is ChatStatus.INSUFFICIENT_EVIDENCE
    assert result.answer is None
    assert result.citations == ()
    assert result.evidence_bundle_ref is None
    assert generator.calls == []


def test_generated_answer_rejects_negative_usage_and_blank_answer() -> None:
    with pytest.raises(ValueError, match="answer"):
        GeneratedAnswer(" ", "model-v1", {"total": 1}, 0.0)

    with pytest.raises(ValueError, match="token_usage"):
        GeneratedAnswer("ok", "model-v1", {"total": -1}, 0.0)
