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


@pytest.mark.parametrize(
    ("task_type", "model_task"),
    [
        ("orchestrator_decision", ModelTask.ORCHESTRATOR_DECISION),
        ("web_search_query_planning", ModelTask.WEB_SEARCH_QUERY_PLAN),
        ("document_search_query_planning", ModelTask.DOCUMENT_SEARCH_QUERY_PLAN),
    ],
)
def test_agent_decision_tasks_reach_the_model_client(task_type: str, model_task: ModelTask) -> None:
    client = FakeClient(ModelResponse(
        task=model_task,
        model="deepseek-v3",
        response_schema=f"structured-{task_type}",
        output={"answer": "ready"},
        source_version="structured-v1",
    ))
    provider = RemoteStructuredLlmProvider(
        client, model="deepseek-v3", mode=StructuredOutputMode.JSON_OBJECT
    )

    result = asyncio.run(provider.generate_structured(
        task_type=task_type,
        system_prompt="Choose the next action.",
        user_prompt="Find the answer.",
        response_model=AnswerPayload,
    ))

    assert result.answer == "ready"
    assert client.request.task is model_task


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
