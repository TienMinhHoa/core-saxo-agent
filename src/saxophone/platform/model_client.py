"""Provider-independent contract for external model-service calls."""

from __future__ import annotations

import asyncio
import inspect
import math
import random
import time
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Callable, Mapping, Protocol

import httpx

from saxophone.platform.observability import EventMetrics, EventSink, StructuredEvent


class ModelValidationError(ValueError):
    """Raised when an external model boundary DTO is unsafe or incomplete."""


class ModelCircuitOpenError(RuntimeError):
    """Raised before transport when the model endpoint is temporarily open."""


class ModelTask(StrEnum):
    PDF_EXTRACT = "pdf_extract"
    FIGURE_ANALYZE = "figure_analyze"
    STRUCTURE_LABEL = "structure_label"
    EMBED = "embed"
    PARAGRAPH_TAG = "paragraph_tag"
    TAG_RESOLVE = "tag_resolve"
    CHUNK_TAGGING = "chunk_tagging"
    RETRIEVAL_SELECT = "retrieval_select"
    ANSWER_GENERATE = "answer_generate"


def _immutable_mapping(
    value: Mapping[str, object],
    field_name: str,
    *,
    validate_json_values: bool = True,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ModelValidationError(f"{field_name} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise ModelValidationError(f"{field_name} keys must be strings")
    if validate_json_values:
        for key, nested_value in value.items():
            _validate_json_value(nested_value, f"{field_name}.{key}")
    return MappingProxyType(dict(value))


def _validate_json_value(value: object, field_name: str) -> None:
    """Reject values that cannot be transported as strict JSON."""

    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        raise ModelValidationError(f"{field_name} must contain finite JSON numbers")
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ModelValidationError(f"{field_name} keys must be strings")
        for key, nested_value in value.items():
            _validate_json_value(nested_value, f"{field_name}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, nested_value in enumerate(value):
            _validate_json_value(nested_value, f"{field_name}[{index}]")
        return
    raise ModelValidationError(f"{field_name} must contain JSON-compatible values")


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Validated request shared by task-specific model adapters."""

    model: str
    task: ModelTask
    input: Mapping[str, object]
    metadata: Mapping[str, object]
    response_schema: str
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        _require_canonical_text("model", self.model)
        if not isinstance(self.task, ModelTask):
            raise ModelValidationError("task must be a ModelTask")
        _require_canonical_text("response_schema", self.response_schema)
        if self.idempotency_key is not None:
            _require_canonical_text("idempotency_key", self.idempotency_key)
        object.__setattr__(self, "input", _immutable_mapping(self.input, "input"))
        object.__setattr__(self, "metadata", _immutable_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """Validated model output before an application adapter commits it."""

    task: ModelTask
    model: str
    response_schema: str
    output: Mapping[str, object]
    source_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.task, ModelTask):
            raise ModelValidationError("task must be a ModelTask")
        _require_canonical_text("model", self.model)
        _require_canonical_text("response_schema", self.response_schema)
        _require_canonical_text("source_version", self.source_version)
        object.__setattr__(
            self,
            "output",
            _immutable_mapping(self.output, "output", validate_json_values=False),
        )


def _require_canonical_text(field_name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or unicodedata.normalize("NFC", value) != value
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise ModelValidationError(f"{field_name} must be canonical text")


def _require_numeric_configuration(
    field_name: str,
    value: object,
    *,
    integer: bool = False,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a numeric value")
    if integer and not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if not math.isfinite(float(value)):
        raise ValueError(f"{field_name} must be finite")


class ModelClient(Protocol):
    """Async port hiding LiteLLM/HTTP transport from application code."""

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        """Execute one typed model request and validate its response."""


class LiteLLMModelClient:
    """Async transport adapter for the repository's LiteLLM-compatible contract.

    The endpoint is injected so the application does not depend on a provider
    URL or on LiteLLM's internal routing.  The adapter only transports and
    validates the typed envelope; task-specific adapters own output mapping.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        http_client: httpx.AsyncClient,
        bearer_token: str,
        timeout_seconds: float = 30.0,
        max_attempts: int = 1,
        retry_backoff_seconds: float = 0.0,
        retry_jitter_ratio: float = 0.0,
        jitter_source: Callable[[float, float], float] = random.uniform,
        circuit_breaker_failure_threshold: int = 0,
        circuit_breaker_cooldown_seconds: float = 30.0,
        monotonic_clock: Callable[[], float] = time.monotonic,
        event_sink: EventSink | None = None,
        metrics: EventMetrics | None = None,
    ) -> None:
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError("endpoint must not be empty")
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in endpoint):
            raise ValueError("endpoint must not contain control characters")
        if not isinstance(bearer_token, str) or not bearer_token.strip():
            raise ValueError("bearer_token must not be empty")
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in bearer_token):
            raise ValueError("bearer_token must not contain control characters")
        if not callable(getattr(http_client, "post", None)):
            raise ValueError("http_client.post must be callable")
        if not callable(jitter_source):
            raise ValueError("jitter_source must be callable")
        if not callable(monotonic_clock):
            raise ValueError("monotonic_clock must be callable")
        _require_numeric_configuration("timeout_seconds", timeout_seconds)
        _require_numeric_configuration("max_attempts", max_attempts, integer=True)
        _require_numeric_configuration("retry_backoff_seconds", retry_backoff_seconds)
        _require_numeric_configuration("retry_jitter_ratio", retry_jitter_ratio)
        _require_numeric_configuration(
            "circuit_breaker_failure_threshold",
            circuit_breaker_failure_threshold,
            integer=True,
        )
        _require_numeric_configuration(
            "circuit_breaker_cooldown_seconds",
            circuit_breaker_cooldown_seconds,
        )
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative")
        if not 0 <= retry_jitter_ratio <= 1:
            raise ValueError("retry_jitter_ratio must be between 0 and 1")
        if circuit_breaker_failure_threshold < 0:
            raise ValueError("circuit_breaker_failure_threshold must not be negative")
        if circuit_breaker_cooldown_seconds <= 0:
            raise ValueError("circuit_breaker_cooldown_seconds must be positive")
        normalized_endpoint = endpoint.strip().rstrip("/")
        if not normalized_endpoint:
            raise ValueError("endpoint must not be empty")
        try:
            parsed_endpoint = httpx.URL(normalized_endpoint)
            parsed_endpoint.port
        except (httpx.InvalidURL, ValueError) as error:
            raise ValueError(
                "endpoint must be an HTTP(S) URL without query, fragment, or invalid port",
            ) from error
        if parsed_endpoint.scheme not in {"http", "https"} or not parsed_endpoint.host:
            raise ValueError("endpoint must be an absolute HTTP(S) URL")
        if parsed_endpoint.username or parsed_endpoint.password:
            raise ValueError("endpoint must not contain user information")
        if parsed_endpoint.query or parsed_endpoint.fragment:
            raise ValueError(
                "endpoint must be an HTTP(S) URL without query, fragment, or invalid port",
            )
        self._endpoint = normalized_endpoint
        self._http_client = http_client
        self._headers = {"Authorization": f"Bearer {bearer_token.strip()}"}
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
        self._retry_jitter_ratio = retry_jitter_ratio
        self._jitter_source = jitter_source
        self._circuit_breaker_failure_threshold = circuit_breaker_failure_threshold
        self._circuit_breaker_cooldown_seconds = circuit_breaker_cooldown_seconds
        self._monotonic_clock = monotonic_clock
        self._event_sink = event_sink
        self._metrics = metrics
        self._consecutive_failures = 0
        self._circuit_opened_at: float | None = None

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @property
    def retry_backoff_seconds(self) -> float:
        return self._retry_backoff_seconds

    @property
    def retry_jitter_ratio(self) -> float:
        return self._retry_jitter_ratio

    @property
    def circuit_breaker_failure_threshold(self) -> int:
        return self._circuit_breaker_failure_threshold

    @property
    def circuit_breaker_cooldown_seconds(self) -> float:
        return self._circuit_breaker_cooldown_seconds

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        started_at = self._monotonic_clock()
        if self._metrics is not None:
            self._metrics.request_started(task=request.task.value)
        attempt_count = 0
        payload = {
            "model": request.model,
            "task_type": request.task.value,
            "input": dict(request.input),
            "metadata": dict(request.metadata),
            "response_format": request.response_schema,
        }
        try:
            try:
                response, attempt_count = await self._post_with_retry(
                    payload,
                    idempotency_key=request.idempotency_key,
                )
            except Exception as error:
                self._emit_event(
                    request,
                    name="model.request.failed",
                    attempt=max(attempt_count, 1),
                    started_at=started_at,
                    result="failure",
                    reason_code=type(error).__name__,
                    output_count=0,
                )
                raise
            try:
                try:
                    payload = response.json()
                except ValueError as error:
                    raise ModelValidationError("model response JSON is invalid") from error
                if not isinstance(payload, Mapping):
                    raise ModelValidationError("model response must be a mapping")
                task = _parse_task(payload.get("task_type"))
                model = _required_text(payload, "model")
                response_schema = _required_text(payload, "response_format")
                _validate_response_identity(
                    request,
                    task=task,
                    model=model,
                    response_schema=response_schema,
                )
                model_response = ModelResponse(
                    task=task,
                    model=model,
                    response_schema=response_schema,
                    output=_required_mapping(payload, "output"),
                    source_version=_required_text(payload, "source_version"),
                )
            except ModelValidationError as error:
                self._emit_event(
                    request,
                    name="model.request.failed",
                    attempt=max(attempt_count, 1),
                    started_at=started_at,
                    result="failure",
                    reason_code=type(error).__name__,
                    output_count=0,
                )
                raise
            self._emit_event(
                request,
                name="model.request.completed",
                attempt=max(attempt_count, 1),
                started_at=started_at,
                result="success",
                reason_code=None,
                output_count=len(model_response.output),
            )
            return model_response
        finally:
            if self._metrics is not None:
                self._metrics.request_finished(task=request.task.value)

    async def _post_with_retry(
        self,
        payload: Mapping[str, object],
        *,
        idempotency_key: str | None,
    ) -> tuple[httpx.Response, int]:
        self._ensure_circuit_closed()
        attempts = self._max_attempts if idempotency_key is not None else 1
        headers = dict(self._headers)
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        for attempt in range(1, attempts + 1):
            retry_delay = _jittered_retry_delay(
                self._retry_backoff_seconds * (2 ** (attempt - 1)),
                ratio=self._retry_jitter_ratio,
                jitter_source=self._jitter_source,
            )
            response: httpx.Response | None = None
            try:
                post_result = self._http_client.post(
                    self._endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self._timeout_seconds,
                )
                if not inspect.isawaitable(post_result):
                    raise ValueError("http_client.post must return an awaitable")
                response = await post_result
                if not isinstance(response, httpx.Response):
                    raise ValueError("http_client.post must return an httpx.Response")
                if response.status_code not in {408, 429, 500, 502, 503, 504}:
                    response.raise_for_status()
                    self._record_success()
                    return response, attempt
                response.raise_for_status()
            except httpx.RequestError:
                self._record_retryable_failure()
                if attempt == attempts:
                    raise
            except httpx.HTTPStatusError:
                if response.status_code in {408, 429, 500, 502, 503, 504}:
                    self._record_retryable_failure()
                if attempt == attempts or response.status_code not in {
                    408,
                    429,
                    500,
                    502,
                    503,
                    504,
                    }:
                    raise
            if response is not None:
                retry_delay = _retry_delay_seconds(
                    response,
                    fallback=retry_delay,
                )
            if retry_delay:
                await asyncio.sleep(retry_delay)
        raise AssertionError("retry loop must return or raise")

    def _emit_event(
        self,
        request: ModelRequest,
        *,
        name: str,
        attempt: int,
        started_at: float,
        result: str,
        reason_code: str | None,
        output_count: int,
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
                model=request.model,
                attempt=attempt,
                duration_ms=round(max(self._monotonic_clock() - started_at, 0.0) * 1000, 3),
                input_count=len(request.input),
                output_count=output_count,
                result=result,
                reason_code=reason_code,
            )
        )

    def _ensure_circuit_closed(self) -> None:
        if self._circuit_opened_at is None:
            return
        if self._monotonic_clock() - self._circuit_opened_at >= self._circuit_breaker_cooldown_seconds:
            self._circuit_opened_at = None
            self._consecutive_failures = 0
            return
        raise ModelCircuitOpenError("model circuit is open")

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_opened_at = None

    def _record_retryable_failure(self) -> None:
        if self._circuit_breaker_failure_threshold == 0:
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._circuit_breaker_failure_threshold:
            self._circuit_opened_at = self._monotonic_clock()


def _retry_delay_seconds(response: httpx.Response, *, fallback: float) -> float:
    """Prefer a valid server delay while retaining the local retry floor."""

    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return fallback
    try:
        server_delay = float(retry_after)
    except ValueError:
        return fallback
    if not math.isfinite(server_delay) or server_delay < 0:
        return fallback
    return max(fallback, server_delay)


def _jittered_retry_delay(
    base_delay: float,
    *,
    ratio: float,
    jitter_source: Callable[[float, float], float],
) -> float:
    """Add bounded positive jitter while preserving the configured delay floor."""

    if not base_delay or not ratio:
        return base_delay
    return base_delay * (1 + jitter_source(0.0, ratio))


def _parse_task(value: object) -> ModelTask:
    try:
        return ModelTask(value)
    except (TypeError, ValueError) as error:
        raise ModelValidationError("model response task_type is invalid") from error


def _required_text(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ModelValidationError(f"model response {name} must be non-blank")
    return value


def _required_mapping(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    if not isinstance(value, Mapping):
        raise ModelValidationError(f"model response {name} must be a mapping")
    return value


def _validate_response_identity(
    request: ModelRequest,
    *,
    task: ModelTask,
    model: str,
    response_schema: str,
) -> None:
    if task is not request.task:
        raise ModelValidationError("model response task_type does not match request")
    if model != request.model:
        raise ModelValidationError("model response model does not match request")
    if response_schema != request.response_schema:
        raise ModelValidationError("model response response_format does not match request")
