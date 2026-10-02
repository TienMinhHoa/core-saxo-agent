from __future__ import annotations

from saxophone.app.factory import AppOverrides, _compose_legacy_chat_services
from saxophone.chat.service import AnswerQuestion
from saxophone.retrieval.use_cases import RetrieveEvidence


class _Retriever:
    async def search(self, query, *, filters=None, limit=10):
        return []


class _AnswerGenerator:
    async def generate(self, question, evidence):
        raise AssertionError("composition test must not invoke the model")


def test_legacy_chat_composition_builds_adapters_from_ports() -> None:
    composition = _compose_legacy_chat_services(
        AppOverrides(
            retriever=_Retriever(),
            answer_generator=_AnswerGenerator(),
        ),
        image_artifact_gate=object(),
    )

    assert isinstance(composition.retrieve_evidence, RetrieveEvidence)
    assert isinstance(composition.answer_question, AnswerQuestion)
    assert composition.answer_question._image_artifact_gate is not None


def test_legacy_chat_composition_preserves_explicit_adapters() -> None:
    retrieve_evidence = object()
    answer_question = object()

    composition = _compose_legacy_chat_services(
        AppOverrides(
            retrieve_evidence=retrieve_evidence,
            answer_question=answer_question,
            retriever=_Retriever(),
            answer_generator=_AnswerGenerator(),
        ),
        image_artifact_gate=object(),
    )

    assert composition.retrieve_evidence is retrieve_evidence
    assert composition.answer_question is answer_question

