from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from saxophone.platform.model_client import ModelResponse, ModelTask
from saxophone.tagging.structured_provider import (
    RemoteStructuredLlmProvider,
    StructuredOutputMode,
)


class AnswerPayload(BaseModel):
    answer: str


class FakeClient:
    def __init__(self, response: ModelResponse) -> None:
        self.response = response
        self.request = None

    async def invoke(self, request):
        self.request = request
        return self.response


def test_structured_provider_maps_task_and_validates_typed_output() -> None:
    client = FakeClient(
        ModelResponse(
            task=ModelTask.ANSWER_GENERATE,
            model="deepseek-v3",
            response_schema="structured-answer_generation",
            output={"answer": "Use the cited paragraph."},
            source_version="structured-v1",
        )
    )
    provider = RemoteStructuredLlmProvider(
        client, model="deepseek-v3", mode=StructuredOutputMode.JSON_OBJECT
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
    assert client.request.task is ModelTask.ANSWER_GENERATE
    assert client.request.input["response_format"] == "json_object"
    assert client.request.input["schema"]["title"] == "AnswerPayload"


def test_json_object_mode_includes_the_output_contract_in_the_prompt() -> None:
    client = FakeClient(
        ModelResponse(
            task=ModelTask.ANSWER_GENERATE,
            model="deepseek-v3",
            response_schema="structured-answer_generation",
            output={"answer": "Use the cited paragraph."},
            source_version="structured-v1",
        )
    )
    provider = RemoteStructuredLlmProvider(
        client, model="deepseek-v3", mode=StructuredOutputMode.JSON_OBJECT
    )

    asyncio.run(
        provider.generate_structured(
            task_type="answer_generation",
            system_prompt="Answer from evidence.",
            user_prompt="What is the rule?",
            response_model=AnswerPayload,
        )
    )

    prompt = client.request.input["user_prompt"]
    assert "Return exactly one JSON object." in prompt
    assert "Do not wrap the object in Markdown fences." in prompt
    assert '"answer"' in prompt


def test_structured_provider_rejects_invalid_typed_output() -> None:
    client = FakeClient(
        ModelResponse(
            task=ModelTask.ANSWER_GENERATE,
            model="deepseek-v3",
            response_schema="structured-answer_generation",
            output={"answer": 12},
            source_version="structured-v1",
        )
    )
    provider = RemoteStructuredLlmProvider(client, model="deepseek-v3")

    with pytest.raises(ValueError, match="structured model output is invalid"):
        asyncio.run(
            provider.generate_structured(
                task_type="answer_generation",
                system_prompt="system",
                user_prompt="user",
                response_model=AnswerPayload,
            )
        )


def test_structured_provider_rejects_unknown_task() -> None:
    provider = RemoteStructuredLlmProvider(FakeClient(None), model="deepseek-v3")

    with pytest.raises(ValueError, match="unsupported structured task_type"):
        asyncio.run(
            provider.generate_structured(
                task_type="unknown_task",
                system_prompt="system",
                user_prompt="user",
                response_model=AnswerPayload,
            )
        )
