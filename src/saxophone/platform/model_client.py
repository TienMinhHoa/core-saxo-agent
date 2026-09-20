"""Provider-independent contract for external model-service calls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, Protocol

import httpx


class ModelValidationError(ValueError):
    """Raised when an external model boundary DTO is unsafe or incomplete."""


class ModelTask(StrEnum):
    PDF_EXTRACT = "pdf_extract"
    FIGURE_ANALYZE = "figure_analyze"
    STRUCTURE_LABEL = "structure_label"
    EMBED = "embed"
    PARAGRAPH_TAG = "paragraph_tag"
    TAG_RESOLVE = "tag_resolve"
    RETRIEVAL_SELECT = "retrieval_select"
    ANSWER_GENERATE = "answer_generate"


def _immutable_mapping(value: Mapping[str, object], field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ModelValidationError(f"{field_name} must be a mapping")
    return MappingProxyType(dict(value))


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Validated request shared by task-specific model adapters."""

    model: str
    task: ModelTask
    input: Mapping[str, object]
    metadata: Mapping[str, object]
    response_schema: str

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise ModelValidationError("model must not be empty")
        if not isinstance(self.task, ModelTask):
            raise ModelValidationError("task must be a ModelTask")
        if not isinstance(self.response_schema, str) or not self.response_schema.strip():
            raise ModelValidationError("response_schema must not be empty")
        object.__setattr__(self, "model", self.model.strip())
        object.__setattr__(self, "response_schema", self.response_schema.strip())
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
        if not isinstance(self.model, str) or not self.model.strip():
            raise ModelValidationError("model must not be empty")
        if not isinstance(self.response_schema, str) or not self.response_schema.strip():
            raise ModelValidationError("response_schema must not be empty")
        if not isinstance(self.source_version, str) or not self.source_version.strip():
            raise ModelValidationError("source_version must not be empty")
        object.__setattr__(self, "model", self.model.strip())
        object.__setattr__(self, "response_schema", self.response_schema.strip())
        object.__setattr__(self, "source_version", self.source_version.strip())
        object.__setattr__(self, "output", _immutable_mapping(self.output, "output"))


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
    ) -> None:
        if not endpoint.strip():
            raise ValueError("endpoint must not be empty")
        if not bearer_token.strip():
            raise ValueError("bearer_token must not be empty")
        self._endpoint = endpoint.rstrip("/")
        self._http_client = http_client
        self._headers = {"Authorization": f"Bearer {bearer_token.strip()}"}

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        response = await self._http_client.post(
            self._endpoint,
            headers=self._headers,
            json={
                "model": request.model,
                "task_type": request.task.value,
                "input": dict(request.input),
                "metadata": dict(request.metadata),
                "response_format": request.response_schema,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ModelValidationError("model response must be a mapping")
        return ModelResponse(
            task=_parse_task(payload.get("task_type")),
            model=_required_text(payload, "model"),
            response_schema=_required_text(payload, "response_format"),
            output=_required_mapping(payload, "output"),
            source_version=_required_text(payload, "source_version"),
        )


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
