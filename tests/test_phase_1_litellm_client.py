from __future__ import annotations

from json import loads

import httpx
import pytest
import anyio

from saxophone.platform.model_client import (
    LiteLLMModelClient,
    ModelCircuitOpenError,
    ModelRequest,
    ModelResponse,
    ModelTask,
    ModelValidationError,
)
from saxophone.platform.observability import EventMetrics, InMemoryEventSink


def _request() -> ModelRequest:
    return ModelRequest(
        model="answer-model-v1",
        task=ModelTask.ANSWER_GENERATE,
        input={"question": "How?"},
        metadata={"source_version": "retrieval-v1"},
        response_schema="answer-v1",
        idempotency_key="answer-test-key",
    )


@pytest.mark.anyio
@pytest.mark.parametrize("ratio", [-0.1, 1.1])
async def test_litellm_client_rejects_invalid_retry_jitter_ratio(ratio: float) -> None:
    async with httpx.AsyncClient() as http_client:
        with pytest.raises(ValueError, match="retry_jitter_ratio"):
            LiteLLMModelClient(
                "https://model.example.test/v1/invoke",
                http_client=http_client,
                bearer_token="secret-token",
                retry_jitter_ratio=ratio,
            )


@pytest.mark.anyio
@pytest.mark.parametrize("bearer_token", ["secret\n-token", "secret\r-token", "secret\x00-token"])
async def test_litellm_client_rejects_control_characters_in_bearer_token(
    bearer_token: str,
) -> None:
    async with httpx.AsyncClient() as http_client:
        with pytest.raises(ValueError, match="bearer_token must not contain control characters"):
            LiteLLMModelClient(
                "https://model.example.test/v1/invoke",
                http_client=http_client,
                bearer_token=bearer_token,
            )


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", [
    "https://model.example.test/v1/invoke\n?redirect=/unsafe",
    "https://model.example.test/v1/invoke\rX-Injected: yes",
    "https://model.example.test/v1/invoke\x00",
])
async def test_litellm_client_rejects_control_characters_in_endpoint(endpoint: str) -> None:
    async with httpx.AsyncClient() as http_client:
        with pytest.raises(ValueError, match="endpoint must not contain control characters"):
            LiteLLMModelClient(
                endpoint,
                http_client=http_client,
                bearer_token="secret-token",
            )


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", ["/", "///", "  ///  "])
async def test_litellm_client_rejects_endpoint_empty_after_normalization(
    endpoint: str,
) -> None:
    async with httpx.AsyncClient() as http_client:
        with pytest.raises(ValueError, match="endpoint must not be empty"):
            LiteLLMModelClient(
                endpoint,
                http_client=http_client,
                bearer_token="secret-token",
            )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timeout_seconds", "30"),
        ("max_attempts", "2"),
        ("retry_backoff_seconds", "1"),
        ("circuit_breaker_failure_threshold", "2"),
        ("circuit_breaker_cooldown_seconds", "30"),
    ],
)
async def test_litellm_client_rejects_non_numeric_configuration_types(
    field: str,
    value: object,
) -> None:
    async with httpx.AsyncClient() as http_client:
        with pytest.raises(ValueError, match=field):
            LiteLLMModelClient(
                "https://model.example.test/v1/invoke",
                http_client=http_client,
                bearer_token="secret-token",
                **{field: value},
            )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timeout_seconds", True),
        ("max_attempts", False),
        ("retry_backoff_seconds", True),
        ("circuit_breaker_failure_threshold", True),
        ("circuit_breaker_cooldown_seconds", False),
    ],
)
async def test_litellm_client_rejects_boolean_numeric_configuration_types(
    field: str,
    value: object,
) -> None:
    async with httpx.AsyncClient() as http_client:
        with pytest.raises(ValueError, match=field):
            LiteLLMModelClient(
                "https://model.example.test/v1/invoke",
                http_client=http_client,
                bearer_token="secret-token",
                **{field: value},
            )


@pytest.mark.anyio
@pytest.mark.parametrize("field", ["jitter_source", "monotonic_clock"])
async def test_litellm_client_rejects_non_callable_injected_dependencies(
    field: str,
) -> None:
    async with httpx.AsyncClient() as http_client:
        with pytest.raises(ValueError, match=field):
            LiteLLMModelClient(
                "https://model.example.test/v1/invoke",
                http_client=http_client,
                bearer_token="secret-token",
                **{field: object()},
            )


@pytest.mark.anyio
@pytest.mark.parametrize("http_client", [object(), type("Transport", (), {"post": object()})()])
async def test_litellm_client_rejects_transport_without_callable_post(http_client: object) -> None:
    with pytest.raises(ValueError, match="http_client.post"):
        LiteLLMModelClient(
            "https://model.example.test/v1/invoke",
            http_client=http_client,  # type: ignore[arg-type]
            bearer_token="secret-token",
        )


@pytest.mark.anyio
async def test_litellm_client_rejects_sync_transport_post_result() -> None:
    class SyncTransport:
        def post(self, *_args: object, **_kwargs: object) -> httpx.Response:
            return httpx.Response(200)

    client = LiteLLMModelClient(
        "https://model.example.test/v1/invoke",
        http_client=SyncTransport(),  # type: ignore[arg-type]
        bearer_token="secret-token",
    )

    with pytest.raises(ValueError, match="http_client.post must return an awaitable"):
        await client.invoke(_request())


@pytest.mark.anyio
async def test_litellm_client_rejects_awaited_transport_result_with_wrong_type() -> None:
    class InvalidResponseTransport:
        async def post(self, *_args, **_kwargs):
            return object()

    client = LiteLLMModelClient(
        "https://model.example.test/v1/invoke",
        http_client=InvalidResponseTransport(),  # type: ignore[arg-type]
        bearer_token="secret-token",
    )

    with pytest.raises(ValueError, match="http_client.post must return an httpx.Response"):
        await client.invoke(_request())


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
    assert requests[0].headers["Idempotency-Key"] == "answer-test-key"
    assert loads(requests[0].content) == {
        "model": "answer-model-v1",
        "task_type": "answer_generate",
        "input": {"question": "How?"},
        "metadata": {"source_version": "retrieval-v1"},
        "response_format": "answer-v1",
    }


@pytest.mark.anyio
async def test_litellm_client_emits_safe_success_event_with_attempt_count() -> None:
    sink = InMemoryEventSink()

    async def handler(_request: httpx.Request) -> httpx.Response:
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
        await LiteLLMModelClient(
            "https://model.example.test/v1/invoke",
            http_client=http_client,
            bearer_token="secret-token",
            event_sink=sink,
        ).invoke(_request())

    event = sink.events[0].as_dict()
    assert event["name"] == "model.request.completed"
    assert event["correlation_id"] == "answer-test-key"
    assert event["task"] == "answer_generate"
    assert event["model"] == "answer-model-v1"
    assert event["attempt"] == 1
    assert event["duration_ms"] >= 0
    assert event["input_count"] == 1
    assert event["output_count"] == 1
    assert event["result"] == "success"


@pytest.mark.anyio
async def test_litellm_client_propagates_cancellation_without_retry_or_stuck_metrics() -> None:
    started = anyio.Event()
    request_count = 0
    metrics = EventMetrics()
    sink = InMemoryEventSink()

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        started.set()
        await anyio.sleep_forever()
        raise AssertionError("the cancelled model request must not return")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = LiteLLMModelClient(
            "https://model.example.test/v1/invoke",
            http_client=http_client,
            bearer_token="secret-token",
            max_attempts=3,
            event_sink=sink,
            metrics=metrics,
        )
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(client.invoke, _request())
            await started.wait()
            task_group.cancel_scope.cancel()

    assert request_count == 1
    assert metrics.in_flight(task="answer_generate") == 0
    assert sink.events == []


@pytest.mark.anyio
async def test_litellm_client_emits_safe_failure_event_without_response_payload() -> None:
    sink = InMemoryEventSink()

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid token"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(httpx.HTTPStatusError):
            await LiteLLMModelClient(
                "https://model.example.test/v1/invoke",
                http_client=http_client,
                bearer_token="secret-token",
                event_sink=sink,
            ).invoke(_request())

    event = sink.events[0].as_dict()
    assert event["name"] == "model.request.failed"
    assert event["correlation_id"] == "answer-test-key"
    assert event["attempt"] == 1
    assert event["result"] == "failure"
    assert event["reason_code"] == "HTTPStatusError"
    assert "response" not in event


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
async def test_litellm_client_exponentially_increases_local_retry_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
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

    monkeypatch.setattr("saxophone.platform.model_client.asyncio.sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        response = await LiteLLMModelClient(
            "https://model.example.test/v1/invoke",
            http_client=http_client,
            bearer_token="secret-token",
            max_attempts=3,
            retry_backoff_seconds=1.5,
        ).invoke(_request())

    assert response.output["answer"] == "Use long tones."
    assert attempts == 3
    assert sleeps == [1.5, 3.0]


@pytest.mark.anyio
async def test_litellm_client_applies_bounded_retry_jitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
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

    monkeypatch.setattr("saxophone.platform.model_client.asyncio.sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        response = await LiteLLMModelClient(
            "https://model.example.test/v1/invoke",
            http_client=http_client,
            bearer_token="secret-token",
            max_attempts=3,
            retry_backoff_seconds=1.5,
            retry_jitter_ratio=0.25,
            jitter_source=lambda _lower, _upper: 0.25,
        ).invoke(_request())

    assert response.output["answer"] == "Use long tones."
    assert attempts == 3
    assert sleeps == [1.875, 3.75]


@pytest.mark.anyio
async def test_litellm_client_retries_network_failure_without_unbound_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("model service timed out")
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

    monkeypatch.setattr("saxophone.platform.model_client.asyncio.sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        response = await LiteLLMModelClient(
            "https://model.example.test/v1/invoke",
            http_client=http_client,
            bearer_token="secret-token",
            max_attempts=2,
            retry_backoff_seconds=1.5,
        ).invoke(_request())

    assert response.output["answer"] == "Use long tones."
    assert attempts == 2
    assert sleeps == [1.5]


@pytest.mark.anyio
async def test_litellm_client_honors_numeric_retry_after_for_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    attempts = 0

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
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

    monkeypatch.setattr("saxophone.platform.model_client.asyncio.sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        response = await LiteLLMModelClient(
            "https://model.example.test/v1/invoke",
            http_client=http_client,
            bearer_token="secret-token",
            max_attempts=2,
            retry_backoff_seconds=1,
        ).invoke(_request())

    assert response.output["answer"] == "Use long tones."
    assert attempts == 2
    assert sleeps == [3.0]


@pytest.mark.anyio
@pytest.mark.parametrize("retry_after", ["not-a-number", "-1", "nan", "inf"])
async def test_litellm_client_uses_local_backoff_for_invalid_retry_after(
    monkeypatch: pytest.MonkeyPatch,
    retry_after: str,
) -> None:
    sleeps: list[float] = []
    attempts = 0

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, headers={"Retry-After": retry_after})
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

    monkeypatch.setattr("saxophone.platform.model_client.asyncio.sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        response = await LiteLLMModelClient(
            "https://model.example.test/v1/invoke",
            http_client=http_client,
            bearer_token="secret-token",
            max_attempts=2,
            retry_backoff_seconds=1,
        ).invoke(_request())

    assert response.output["answer"] == "Use long tones."
    assert attempts == 2
    assert sleeps == [1.0]


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
async def test_litellm_client_does_not_retry_without_idempotency_key() -> None:
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"detail": "busy"})

    request = ModelRequest(
        model="answer-model-v1",
        task=ModelTask.ANSWER_GENERATE,
        input={"question": "How?"},
        metadata={"source_version": "retrieval-v1"},
        response_schema="answer-v1",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(httpx.HTTPStatusError):
            await LiteLLMModelClient(
                "https://model.example.test/v1/invoke",
                http_client=http_client,
                bearer_token="secret-token",
                max_attempts=3,
            ).invoke(request)

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
