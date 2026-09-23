"""Direct DeepSeek chat and OpenAI embedding transport adapters."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import time
from typing import Callable

import httpx

from saxophone.platform.model_client import (
    ModelClient,
    ModelRequest,
    ModelResponse,
    ModelTask,
    ModelValidationError,
)
from saxophone.platform.model_pricing import (
    estimate_model_cost_usd,
    pricing_basis_for_model,
)
from saxophone.platform.observability import EventMetrics, EventSink, StructuredEvent

_DEEPSEEK_TASKS = {
    ModelTask.CHUNK_TAGGING,
    ModelTask.RETRIEVAL_SELECT,
    ModelTask.ANSWER_GENERATE,
}
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


@dataclass(frozen=True, slots=True)
class _ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int = 0

    def estimated_cost_usd(self, model: str) -> float | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return estimate_model_cost_usd(
            model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cached_input_tokens=self.cached_input_tokens,
        )


class _BilledResponseValidationError(ModelValidationError):
    def __init__(
        self,
        message: str,
        *,
        usage: _ProviderUsage,
        attempt: int,
    ) -> None:
        super().__init__(message)
        self.usage = usage
        self.attempt = attempt


class DirectApiModelClient(ModelClient):
    """Route typed model requests directly to official provider APIs."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        deepseek_api_base_url: str,
        deepseek_api_key: str,
        deepseek_model: str,
        deepseek_reasoning_effort: str,
        deepseek_max_tokens: int,
        openai_api_base_url: str,
        openai_api_key: str,
        openai_embedding_model: str,
        embedding_dimension: int,
        timeout_seconds: float = 300.0,
        max_attempts: int = 2,
        retry_backoff_seconds: float = 1.0,
        event_sink: EventSink | None = None,
        metrics: EventMetrics | None = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not callable(getattr(http_client, "post", None)):
            raise TypeError("http_client.post must be callable")
        self._deepseek_url = _provider_url(
            deepseek_api_base_url,
            "chat/completions",
            "deepseek_api_base_url",
        )
        self._openai_url = _provider_url(
            openai_api_base_url,
            "embeddings",
            "openai_api_base_url",
        )
        self._deepseek_headers = _provider_headers(deepseek_api_key, "deepseek_api_key")
        self._openai_headers = _provider_headers(openai_api_key, "openai_api_key")
        self._deepseek_model = _required_text(deepseek_model, "deepseek_model")
        if deepseek_reasoning_effort not in {"low", "high", "max"}:
            raise ValueError("deepseek_reasoning_effort must be low, high, or max")
        self._deepseek_reasoning_effort = deepseek_reasoning_effort
        self._deepseek_max_tokens = _positive_integer(
            deepseek_max_tokens,
            "deepseek_max_tokens",
        )
        self._openai_embedding_model = _required_text(
            openai_embedding_model,
            "openai_embedding_model",
        )
        self._embedding_dimension = _positive_integer(
            embedding_dimension,
            "embedding_dimension",
        )
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
            raise ValueError("timeout_seconds must be positive")
        if not math.isfinite(float(timeout_seconds)) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = float(timeout_seconds)
        self._max_attempts = _positive_integer(max_attempts, "max_attempts")
        if (
            isinstance(retry_backoff_seconds, bool)
            or not isinstance(retry_backoff_seconds, (int, float))
            or not math.isfinite(float(retry_backoff_seconds))
            or retry_backoff_seconds < 0
        ):
            raise ValueError("retry_backoff_seconds must be non-negative")
        self._retry_backoff_seconds = float(retry_backoff_seconds)
        if not callable(monotonic_clock):
            raise ValueError("monotonic_clock must be callable")
        self._event_sink = event_sink
        self._metrics = metrics
        self._monotonic_clock = monotonic_clock
        self._http_client = http_client

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        if not isinstance(request, ModelRequest):
            raise TypeError("request must be a ModelRequest")
        started_at = self._monotonic_clock()
        if self._metrics is not None:
            self._metrics.request_started(task=request.task.value)
        provider_model = self._provider_model(request.task)
        attempt_count = 0
        usage = _ProviderUsage()
        try:
            try:
                if request.task is ModelTask.EMBED:
                    output, usage, attempt_count = await self._embed(request)
                elif request.task in _DEEPSEEK_TASKS:
                    output, usage, attempt_count = await self._generate_structured(request)
                else:
                    raise ModelValidationError(
                        f"direct provider does not support task: {request.task.value}"
                    )
                source_version = request.metadata.get(
                    "source_version",
                    "direct-provider-v1",
                )
                if not isinstance(source_version, str) or not source_version.strip():
                    raise ModelValidationError("request source_version must be non-blank")
                model_response = ModelResponse(
                    task=request.task,
                    model=request.model,
                    response_schema=request.response_schema,
                    output=output,
                    source_version=source_version,
                )
            except Exception as error:
                if isinstance(error, _BilledResponseValidationError):
                    usage = error.usage
                    attempt_count = error.attempt
                self._emit_event(
                    request,
                    provider_model=provider_model,
                    name="model.request.failed",
                    attempt=max(attempt_count, 1),
                    started_at=started_at,
                    output_count=0,
                    result="failure",
                    reason_code=(
                        ModelValidationError.__name__
                        if isinstance(error, _BilledResponseValidationError)
                        else type(error).__name__
                    ),
                    usage=usage,
                )
                raise
            self._emit_event(
                request,
                provider_model=provider_model,
                name="model.request.completed",
                attempt=max(attempt_count, 1),
                started_at=started_at,
                output_count=len(model_response.output),
                result="success",
                reason_code=None,
                usage=usage,
            )
            return model_response
        finally:
            if self._metrics is not None:
                self._metrics.request_finished(task=request.task.value)

    async def _embed(
        self,
        request: ModelRequest,
    ) -> tuple[Mapping[str, object], _ProviderUsage, int]:
        source_version = request.metadata.get("source_version")
        if not isinstance(source_version, str) or not source_version.strip():
            raise ModelValidationError("embedding source_version must be non-blank")
        chunk_ids, texts = _embedding_inputs(request.input.get("texts"))
        response, attempt = await self._post_json(
            self._openai_url,
            headers=self._openai_headers,
            idempotency_key=request.idempotency_key,
            payload={
                "model": self._openai_embedding_model,
                "input": texts,
                "dimensions": self._embedding_dimension,
                "encoding_format": "float",
            },
        )
        usage = _provider_usage(response, embedding=True)
        try:
            data = _required_list(response, "data", "OpenAI embedding response")
            if len(data) != len(chunk_ids):
                raise ModelValidationError("embedding response count does not match request")
            indexed_vectors: dict[int, list[float]] = {}
            for item in data:
                if not isinstance(item, Mapping):
                    raise ModelValidationError("embedding response item must be a mapping")
                index = item.get("index")
                if isinstance(index, bool) or not isinstance(index, int):
                    raise ModelValidationError("embedding response index must be an integer")
                if index in indexed_vectors:
                    raise ModelValidationError("embedding response indexes must be unique")
                indexed_vectors[index] = _embedding_vector(
                    item.get("embedding"),
                    dimension=self._embedding_dimension,
                )
            if set(indexed_vectors) != set(range(len(chunk_ids))):
                raise ModelValidationError("embedding response indexes do not match request")
            output = {
                "embeddings": [
                    {"chunk_id": chunk_id, "vector": indexed_vectors[index]}
                    for index, chunk_id in enumerate(chunk_ids)
                ]
            }
        except ModelValidationError as error:
            raise _BilledResponseValidationError(
                str(error),
                usage=usage,
                attempt=attempt,
            ) from error
        return output, usage, attempt

    async def _generate_structured(
        self,
        request: ModelRequest,
    ) -> tuple[Mapping[str, object], _ProviderUsage, int]:
        system_prompt = _mapping_text(request.input, "system_prompt")
        user_prompt = _mapping_text(request.input, "user_prompt")
        if request.input.get("response_format") != "json_object":
            raise ModelValidationError(
                "DeepSeek direct provider requires json_object structured output"
            )
        response, attempt = await self._post_json(
            self._deepseek_url,
            headers=self._deepseek_headers,
            idempotency_key=request.idempotency_key,
            payload={
                "model": self._deepseek_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "thinking": {"type": "enabled"},
                "reasoning_effort": self._deepseek_reasoning_effort,
                "max_tokens": self._deepseek_max_tokens,
                "stream": False,
            },
        )
        usage = _provider_usage(response, embedding=False)
        try:
            choices = _required_list(response, "choices", "DeepSeek response")
            if not choices or not isinstance(choices[0], Mapping):
                raise ModelValidationError("DeepSeek response choices must not be empty")
            message = choices[0].get("message")
            if not isinstance(message, Mapping):
                raise ModelValidationError("DeepSeek response message must be a mapping")
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ModelValidationError("DeepSeek response content must be non-blank")
            try:
                output = json.loads(content)
            except json.JSONDecodeError as error:
                raise ModelValidationError(
                    "DeepSeek response content must be valid JSON"
                ) from error
            if not isinstance(output, Mapping):
                raise ModelValidationError("DeepSeek structured output must be a mapping")
        except ModelValidationError as error:
            raise _BilledResponseValidationError(
                str(error),
                usage=usage,
                attempt=attempt,
            ) from error
        return dict(output), usage, attempt

    async def _post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        idempotency_key: str | None,
        payload: Mapping[str, object],
    ) -> tuple[Mapping[str, object], int]:
        request_headers = dict(headers)
        if idempotency_key is not None:
            request_headers["Idempotency-Key"] = idempotency_key
        response: httpx.Response | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._http_client.post(
                    url,
                    headers=request_headers,
                    json=dict(payload),
                    timeout=self._timeout_seconds,
                )
                if response.status_code not in _RETRYABLE_STATUS_CODES:
                    response.raise_for_status()
                    return _json_mapping(response), attempt
                response.raise_for_status()
            except httpx.RequestError:
                if attempt == self._max_attempts:
                    raise
            except httpx.HTTPStatusError:
                if response is None or response.status_code not in _RETRYABLE_STATUS_CODES:
                    raise
                if attempt == self._max_attempts:
                    raise
            delay = _retry_delay(
                response,
                fallback=self._retry_backoff_seconds * (2 ** (attempt - 1)),
            )
            if delay:
                await asyncio.sleep(delay)
        raise AssertionError("provider retry loop must return or raise")

    def _provider_model(self, task: ModelTask) -> str:
        if task is ModelTask.EMBED:
            return self._openai_embedding_model
        return self._deepseek_model

    def _emit_event(
        self,
        request: ModelRequest,
        *,
        provider_model: str,
        name: str,
        attempt: int,
        started_at: float,
        output_count: int,
        result: str,
        reason_code: str | None,
        usage: _ProviderUsage,
    ) -> None:
        if self._event_sink is None:
            return
        correlation_id = str(
            request.metadata.get("correlation_id")
            or request.idempotency_key
            or "model-request"
        )
        self._event_sink.emit(
            StructuredEvent(
                name=name,
                correlation_id=correlation_id,
                task=request.task.value,
                model=provider_model,
                attempt=attempt,
                duration_ms=round(
                    max(self._monotonic_clock() - started_at, 0.0) * 1000,
                    3,
                ),
                input_count=_input_count(request),
                output_count=output_count,
                result=result,
                reason_code=reason_code,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=usage.estimated_cost_usd(provider_model),
                pricing_basis=(
                    pricing_basis_for_model(provider_model)
                    if usage.input_tokens is not None
                    else None
                ),
            )
        )


def _provider_url(base_url: str, suffix: str, field_name: str) -> str:
    normalized = _required_text(base_url, field_name).rstrip("/")
    try:
        parsed = httpx.URL(normalized)
        parsed.port
    except (httpx.InvalidURL, ValueError) as error:
        raise ValueError(f"{field_name} must be an HTTPS URL") from error
    if parsed.scheme != "https" or not parsed.host or parsed.query or parsed.fragment:
        raise ValueError(f"{field_name} must be an HTTPS URL")
    return f"{normalized}/{suffix}"


def _provider_headers(api_key: str, field_name: str) -> dict[str, str]:
    key = _required_text(api_key, field_name)
    if any(ord(character) < 32 or ord(character) == 127 for character in key):
        raise ValueError(f"{field_name} must not contain control characters")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _positive_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{field_name} must be canonical non-blank text")
    return value


def _mapping_text(value: Mapping[str, object], field_name: str) -> str:
    try:
        return _required_text(value.get(field_name), field_name)
    except ValueError as error:
        raise ModelValidationError(str(error)) from error


def _embedding_inputs(value: object) -> tuple[list[str], list[str]]:
    if not isinstance(value, list) or not value:
        raise ModelValidationError("embedding request texts must be a non-empty list")
    chunk_ids: list[str] = []
    texts: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ModelValidationError("embedding request item must be a mapping")
        try:
            chunk_ids.append(_required_text(item.get("chunk_id"), "chunk_id"))
            texts.append(_required_text(item.get("text"), "text"))
        except ValueError as error:
            raise ModelValidationError(str(error)) from error
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ModelValidationError("embedding request chunk IDs must be unique")
    return chunk_ids, texts


def _required_list(
    value: Mapping[str, object],
    field_name: str,
    context: str,
) -> list[object]:
    result = value.get(field_name)
    if not isinstance(result, list):
        raise ModelValidationError(f"{context} {field_name} must be a list")
    return result


def _embedding_vector(value: object, *, dimension: int) -> list[float]:
    if not isinstance(value, list) or len(value) != dimension:
        raise ModelValidationError("embedding vector dimension does not match configuration")
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(float(item))
        for item in value
    ):
        raise ModelValidationError("embedding vector values must be finite numbers")
    return [float(item) for item in value]


def _json_mapping(response: httpx.Response) -> Mapping[str, object]:
    try:
        payload = response.json()
    except ValueError as error:
        raise ModelValidationError("provider response JSON is invalid") from error
    if not isinstance(payload, Mapping):
        raise ModelValidationError("provider response must be a mapping")
    return payload


def _provider_usage(
    response: Mapping[str, object],
    *,
    embedding: bool,
) -> _ProviderUsage:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return _ProviderUsage(output_tokens=0 if embedding else None)
    input_tokens = _token_count(usage, "prompt_tokens", "input_tokens")
    output_tokens = _token_count(usage, "completion_tokens", "output_tokens")
    if embedding and output_tokens is None:
        output_tokens = 0
    cached_input_tokens = _cached_input_tokens(usage, input_tokens)
    return _ProviderUsage(input_tokens, output_tokens, cached_input_tokens)


def _token_count(usage: Mapping[str, object], *field_names: str) -> int | None:
    for field_name in field_names:
        value = usage.get(field_name)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def _cached_input_tokens(
    usage: Mapping[str, object],
    input_tokens: int | None,
) -> int:
    if input_tokens is None:
        return 0
    cached = _token_count(usage, "prompt_cache_hit_tokens", "cached_input_tokens")
    details = usage.get("prompt_tokens_details")
    if cached is None and isinstance(details, Mapping):
        cached = _token_count(details, "cached_tokens")
    if cached is None or cached > input_tokens:
        return 0
    return cached


def _input_count(request: ModelRequest) -> int:
    if request.task is ModelTask.EMBED:
        texts = request.input.get("texts")
        if isinstance(texts, list):
            return len(texts)
    return len(request.input)


def _retry_delay(response: httpx.Response | None, *, fallback: float) -> float:
    if response is None:
        return fallback
    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return fallback
    try:
        delay = float(retry_after)
    except ValueError:
        return fallback
    if not math.isfinite(delay) or delay < 0:
        return fallback
    return max(delay, fallback)
