from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from saxophone.tagging.structured_provider import (
    FakeStructuredLlmProvider,
    StructuredOutputMode,
)


class AnswerPayload(BaseModel):
    answer: str


def test_fake_structured_provider_returns_validated_typed_output() -> None:
    provider = FakeStructuredLlmProvider(
        {"answer_generation": {"answer": "Use the cited paragraph."}}
    )

    result = asyncio.run(
        provider.generate_structured(
            task_type="answer_generation",
            system_prompt="Answer from evidence.",
            user_prompt="What is the rule?",
            response_model=AnswerPayload,
        )
    )

    assert result == AnswerPayload(answer="Use the cited paragraph.")
    assert provider.structured_output_mode is StructuredOutputMode.JSON_OBJECT


def test_fake_structured_provider_rejects_missing_or_invalid_responses() -> None:
    provider = FakeStructuredLlmProvider({"answer_generation": {"answer": 12}})

    with pytest.raises(ValueError, match="structured model output is invalid"):
        asyncio.run(
            provider.generate_structured(
                task_type="answer_generation",
                system_prompt="system",
                user_prompt="user",
                response_model=AnswerPayload,
            )
        )

    with pytest.raises(ValueError, match="no fake response configured"):
        asyncio.run(
            provider.generate_structured(
                task_type="concept_role_selection",
                system_prompt="system",
                user_prompt="user",
                response_model=AnswerPayload,
            )
        )


def test_fake_structured_provider_applies_same_task_and_prompt_contract() -> None:
    provider = FakeStructuredLlmProvider({"answer_generation": {"answer": "ok"}})

    with pytest.raises(ValueError, match="unsupported structured task_type"):
        asyncio.run(
            provider.generate_structured(
                task_type="unknown",
                system_prompt="system",
                user_prompt="user",
                response_model=AnswerPayload,
            )
        )

    with pytest.raises(ValueError, match="system_prompt"):
        asyncio.run(
            provider.generate_structured(
                task_type="answer_generation",
                system_prompt=" system",
                user_prompt="user",
                response_model=AnswerPayload,
            )
        )
