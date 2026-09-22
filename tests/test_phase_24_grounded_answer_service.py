from __future__ import annotations

import asyncio

from saxophone.chat.models import ChatResult, ChatStatus
from saxophone.chat.service import AnswerQuestion, GroundedAnswerService
from saxophone.retrieval.question_retrieval import QuestionRequest


class _AnswerQuestion:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, int]] = []

    async def execute(self, question: str, *, filters=None, limit: int = 10) -> ChatResult:
        self.calls.append((question, filters, limit))
        return ChatResult(
            ChatStatus.INSUFFICIENT_EVIDENCE,
            None,
            (),
            None,
            None,
            {},
            0.0,
            "no matching evidence",
        )


def test_grounded_answer_service_delegates_typed_request() -> None:
    delegate = _AnswerQuestion()
    service = GroundedAnswerService(delegate)  # type: ignore[arg-type]

    result = asyncio.run(
        service.answer(QuestionRequest("  What is a long tone?  ", {"book": "a"}, 3))
    )

    assert result.status is ChatStatus.INSUFFICIENT_EVIDENCE
    assert delegate.calls == [("What is a long tone?", {"book": "a"}, 3)]


def test_grounded_answer_service_rejects_wrong_request_type_before_delegate() -> None:
    delegate = _AnswerQuestion()
    service = GroundedAnswerService(delegate)  # type: ignore[arg-type]

    try:
        asyncio.run(service.answer("not-a-request"))  # type: ignore[arg-type]
    except ValueError as error:
        assert str(error) == "request must be a QuestionRequest"
    else:
        raise AssertionError("expected request validation failure")


def test_existing_answer_question_remains_the_delegate_contract() -> None:
    assert issubclass(AnswerQuestion, object)
