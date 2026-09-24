"""Typed structured-output provider boundary for DeepSeek-compatible clients."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from collections.abc import Mapping
from typing import Any, Protocol, TypeVar

from saxophone.platform.model_client import ModelClient, ModelRequest, ModelTask, ModelValidationError


class StructuredOutputMode(StrEnum):
    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"


T = TypeVar("T")


class StructuredModel(Protocol[T]):
    @classmethod
    def model_json_schema(cls) -> dict[str, object]: ...

    @classmethod
    def model_validate(cls, value: object) -> T: ...


class StructuredLlmProvider(Protocol):
    @property
    def structured_output_mode(self) -> StructuredOutputMode: ...

    async def generate_structured(
        self,
        *,
        task_type: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T: ...


_TASKS: dict[str, ModelTask] = {
    "chunk_tagging_and_conflict": ModelTask.CHUNK_TAGGING,
    "concept_role_selection": ModelTask.RETRIEVAL_SELECT,
    "paragraph_selection": ModelTask.RETRIEVAL_SELECT,
    "answer_generation": ModelTask.ANSWER_GENERATE,
}


class RemoteStructuredLlmProvider:
    """Adapt the existing model client to a typed structured-output contract."""

    def __init__(
        self,
        client: ModelClient,
        *,
        model: str,
        mode: StructuredOutputMode = StructuredOutputMode.JSON_SCHEMA,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must not be empty")
        if not isinstance(mode, StructuredOutputMode):
            raise ValueError("mode must be a StructuredOutputMode")
        self._client = client
        self._model = model.strip()
        self._mode = mode

    @property
    def structured_output_mode(self) -> StructuredOutputMode:
        return self._mode

    async def generate_structured(
        self,
        *,
        task_type: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        task = _TASKS.get(task_type)
        if task is None:
            raise ValueError(f"unsupported structured task_type: {task_type}")
        _require_prompt("system_prompt", system_prompt)
        _require_prompt("user_prompt", user_prompt)
        schema_factory = getattr(response_model, "model_json_schema", None)
        validator = getattr(response_model, "model_validate", None)
        if not callable(schema_factory) or not callable(validator):
            raise TypeError("response_model must implement the structured model contract")
        schema = schema_factory()
        if not isinstance(schema, dict):
            raise TypeError("response_model schema must be a mapping")
        request_prompt = _structured_user_prompt(
            user_prompt,
            schema=schema,
            mode=self._mode,
        )
        request = ModelRequest(
            model=self._model,
            task=task,
            input={
                "system_prompt": system_prompt,
                "user_prompt": request_prompt,
                "response_format": self._mode.value,
                "schema": schema,
            },
            metadata={"source_version": "structured-v1", "task_type": task_type},
            response_schema=f"structured-{task_type}",
            idempotency_key=_request_key(task_type, system_prompt, user_prompt),
        )
        response = await self._client.invoke(request)
        if response.task is not task or response.response_schema != request.response_schema:
            raise ModelValidationError("structured response identity is invalid")
        try:
            return validator(dict(response.output))
        except Exception as error:
            raise ValueError("structured model output is invalid") from error


class FakeStructuredLlmProvider:
    """Deterministic structured provider for unit and integration tests."""

    def __init__(self, responses: Mapping[str, object]) -> None:
        if not isinstance(responses, Mapping):
            raise ValueError("responses must be a mapping")
        unknown = set(responses) - set(_TASKS)
        if unknown:
            raise ValueError(f"unsupported structured task_type: {sorted(unknown)[0]}")
        self._responses = dict(responses)

    @property
    def structured_output_mode(self) -> StructuredOutputMode:
        return StructuredOutputMode.JSON_OBJECT

    async def generate_structured(
        self,
        *,
        task_type: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        if task_type not in _TASKS:
            raise ValueError(f"unsupported structured task_type: {task_type}")
        _require_prompt("system_prompt", system_prompt)
        _require_prompt("user_prompt", user_prompt)
        validator = getattr(response_model, "model_validate", None)
        if not callable(validator):
            raise TypeError("response_model must implement the structured model contract")
        if task_type not in self._responses:
            raise ValueError(f"no fake response configured for task_type: {task_type}")
        try:
            return validator(self._responses[task_type])
        except Exception as error:
            raise ValueError("structured model output is invalid") from error


def _require_prompt(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{field_name} must be non-blank canonical text")


def _request_key(task_type: str, system_prompt: str, user_prompt: str) -> str:
    payload = json.dumps(
        [task_type, system_prompt, user_prompt], ensure_ascii=False, separators=(",", ":")
    )
    return f"structured-{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _structured_user_prompt(
    user_prompt: str,
    *,
    schema: dict[str, object],
    mode: StructuredOutputMode,
) -> str:
    """Attach an explicit output contract when native schemas are unavailable."""

    if mode is StructuredOutputMode.JSON_SCHEMA:
        return user_prompt
    contract = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    return "\n\n".join(
        (
            user_prompt,
            "Output contract:\n"
            "Return exactly one JSON object.\n"
            "Do not wrap the object in Markdown fences.\n"
            "Do not include explanatory text before or after the JSON object.\n"
            "Use only the keys and enum values defined in this JSON Schema:\n"
            f"{contract}",
        )
    )
