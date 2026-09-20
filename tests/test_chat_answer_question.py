from __future__ import annotations

import pytest

from saxophone.chat.models import ChatResult, ChatStatus, GeneratedAnswer
from saxophone.chat.service import AnswerQuestion
from saxophone.platform.artifacts import SafeImageArtifactGate
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
    assert result.insufficiency_reason == "no matching evidence"
    assert generator.calls == []


def test_generated_answer_rejects_negative_usage_and_blank_answer() -> None:
    with pytest.raises(ValueError, match="answer"):
        GeneratedAnswer(" ", "model-v1", {"total": 1}, 0.0)

    with pytest.raises(ValueError, match="token_usage"):
        GeneratedAnswer("ok", "model-v1", {"total": -1}, 0.0)


def test_chat_result_rejects_malformed_token_usage() -> None:
    base = {
        "status": ChatStatus.ANSWERED,
        "answer": "Use long tones first.",
        "citations": ("book-1",),
        "evidence_bundle_ref": "evidence://retrieval-v1/ref",
        "model_version": "answer-model-v1",
        "cost": 0.0,
    }

    with pytest.raises(ValueError, match="token_usage"):
        ChatResult(**base, token_usage={"total": -1})
    with pytest.raises(ValueError, match="token_usage"):
        ChatResult(**base, token_usage={"total": True})
    with pytest.raises(ValueError, match="token_usage"):
        ChatResult(**base, token_usage={" ": 1})


def test_chat_result_rejects_mutable_or_untyped_citations() -> None:
    base = {
        "status": ChatStatus.ANSWERED,
        "answer": "Use long tones first.",
        "evidence_bundle_ref": "evidence://retrieval-v1/ref",
        "model_version": "answer-model-v1",
        "token_usage": {"total": 1},
        "cost": 0.0,
    }

    with pytest.raises(ValueError, match="citations"):
        ChatResult(**base, citations=["book-1"])
    with pytest.raises(ValueError, match="citations"):
        ChatResult(**base, citations="book-1")


def test_chat_result_rejects_citations_when_evidence_is_insufficient() -> None:
    with pytest.raises(ValueError, match="citations"):
        ChatResult(
            status=ChatStatus.INSUFFICIENT_EVIDENCE,
            answer=None,
            citations=("book-1",),
            evidence_bundle_ref=None,
            model_version=None,
            token_usage={},
            cost=0.0,
            insufficiency_reason="no matching evidence",
        )


@pytest.mark.anyio
async def test_answer_question_requires_a_safe_gate_for_image_evidence() -> None:
    class ImageRetriever(_Retriever):
        async def search(self, query: str, *, filters=None, limit: int = 10):
            return [ChunkHit("book-1", "chunk-1", 1, "retrieval-v1", {
                "document": "See the fingering chart.", "image_refs": ["../secret.png"]
            }, semantic_score=0.9)]

    generator = _AnswerGenerator()
    with pytest.raises(ValueError, match="image artifact gate"):
        await AnswerQuestion(RetrieveEvidence(ImageRetriever([])), generator).execute("How?")
    assert generator.calls == []


@pytest.mark.anyio
async def test_answer_question_passes_only_gated_image_refs_to_generator() -> None:
    class ImageRetriever(_Retriever):
        async def search(self, query: str, *, filters=None, limit: int = 10):
            return [ChunkHit("book-1", "chunk-1", 1, "retrieval-v1", {
                "document": "See the fingering chart.", "image_refs": ["images/page-1.png"]
            }, semantic_score=0.9)]

    generator = _AnswerGenerator()
    await AnswerQuestion(
        RetrieveEvidence(ImageRetriever([])), generator,
        image_artifact_gate=SafeImageArtifactGate(),
    ).execute("How?")
    assert generator.calls[0][1].image_refs == ("images/page-1.png",)


@pytest.mark.anyio
async def test_safe_image_artifact_gate_rejects_absolute_and_remote_refs() -> None:
    gate = SafeImageArtifactGate()
    with pytest.raises(ValueError, match="safe image reference"):
        await gate.validate(("C:/secret.png",))
    with pytest.raises(ValueError, match="safe image reference"):
        await gate.validate(("https://example.test/image.png",))
