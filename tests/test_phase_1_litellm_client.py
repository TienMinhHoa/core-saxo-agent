from __future__ import annotations

from json import loads

import httpx
import pytest

from saxophone.platform.model_client import (
    LiteLLMModelClient,
    ModelCircuitOpenError,
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
async def test_litellm_client_maps_malformed_json_to_model_validation_error() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(ModelValidationError, match="JSON"):
            await LiteLLMModelClient(
                "https://model.example.test/v1/invoke",
                http_client=http_client,
                bearer_token="secret-token",
            ).invoke(_request())


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task_type", "embed"),
        ("model", "different-model"),
        ("response_format", "different-schema"),
    ],
)
async def test_litellm_client_rejects_response_identity_mismatch(
    field: str,
    value: str,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        payload = {
            "task_type": "answer_generate",
            "model": "answer-model-v1",
            "response_format": "answer-v1",
            "output": {"answer": "Use long tones."},
            "source_version": "model-source-v1",
        }
        payload[field] = value
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(ModelValidationError, match=field):
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


@pytest.mark.anyio
async def test_litellm_client_retries_transient_http_failure_with_bounded_attempts() -> None:
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, json={"detail": "busy"})
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
            timeout_seconds=2.5,
            max_attempts=2,
        ).invoke(_request())

    assert response.output["answer"] == "Use long tones."
    assert attempts == 2


@pytest.mark.anyio
async def test_litellm_client_does_not_retry_contract_or_auth_failures() -> None:
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, json={"detail": "invalid token"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(httpx.HTTPStatusError):
            await LiteLLMModelClient(
                "https://model.example.test/v1/invoke",
                http_client=http_client,
                bearer_token="secret-token",
                max_attempts=3,
            ).invoke(_request())

    assert attempts == 1


@pytest.mark.anyio
async def test_litellm_client_opens_circuit_after_retryable_failures_and_recovers() -> None:
    attempts = 0
    now = 10.0

    def clock() -> float:
        return now

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"detail": "busy"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = LiteLLMModelClient(
            "https://model.example.test/v1/invoke",
            http_client=http_client,
            bearer_token="secret-token",
            circuit_breaker_failure_threshold=2,
            circuit_breaker_cooldown_seconds=5,
            monotonic_clock=clock,
        )
        for _ in range(2):
            with pytest.raises(httpx.HTTPStatusError):
                await client.invoke(_request())
        with pytest.raises(ModelCircuitOpenError):
            await client.invoke(_request())
        assert attempts == 2

        now = 15.0
        with pytest.raises(httpx.HTTPStatusError):
            await client.invoke(_request())
        assert attempts == 3
