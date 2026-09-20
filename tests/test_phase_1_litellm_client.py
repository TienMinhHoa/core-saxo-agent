from __future__ import annotations

from json import loads

import httpx
import pytest

from saxophone.platform.model_client import (
    LiteLLMModelClient,
    ModelRequest,
    ModelResponse,
    ModelTask,
    ModelValidationError,
)


def _request() -> ModelRequest:
    return ModelRequest(
        model="answer-model-v1",
        task=ModelTask.ANSWER_GENERATE,
        input={"question": "How?"},
        metadata={"source_version": "retrieval-v1"},
        response_schema="answer-v1",
    )


@pytest.mark.anyio
async def test_litellm_client_sends_typed_envelope_and_maps_response() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "task_type": "answer_generate",
                "model": "answer-model-v1",
                "response_format": "answer-v1",
                "output": {"answer": "Use long tones."},
                "source_version": "model-source-v1",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        response = await LiteLLMModelClient(
            "https://model.example.test/v1/invoke",
            http_client=http_client,
            bearer_token="secret-token",
        ).invoke(_request())

    assert isinstance(response, ModelResponse)
    assert response.task is ModelTask.ANSWER_GENERATE
    assert requests[0].headers["Authorization"] == "Bearer secret-token"
    assert loads(requests[0].content) == {
        "model": "answer-model-v1",
        "task_type": "answer_generate",
        "input": {"question": "How?"},
        "metadata": {"source_version": "retrieval-v1"},
        "response_format": "answer-v1",
    }


@pytest.mark.anyio
async def test_litellm_client_rejects_invalid_typed_response() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"task_type": "unknown"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(ModelValidationError, match="task_type"):
            await LiteLLMModelClient(
                "https://model.example.test/v1/invoke",
                http_client=http_client,
                bearer_token="secret-token",
            ).invoke(_request())


@pytest.mark.anyio
async def test_litellm_client_propagates_http_failure_without_job_translation() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "unavailable"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(httpx.HTTPStatusError):
            await LiteLLMModelClient(
                "https://model.example.test/v1/invoke",
                http_client=http_client,
                bearer_token="secret-token",
            ).invoke(_request())
