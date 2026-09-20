from __future__ import annotations

import asyncio

import pytest

from saxophone.platform.model_client import (
    ModelRequest,
    ModelResponse,
    ModelTask,
    ModelValidationError,
)


def test_model_request_preserves_typed_task_and_immutable_payload() -> None:
    request = ModelRequest(
        model="extractor-v1",
        task=ModelTask.PDF_EXTRACT,
        input={"document_ref": "doc-1"},
        metadata={"source_version": "sha256:abc"},
        response_schema="pdf-extraction-v1",
        idempotency_key=" correlation-1 ",
    )

    assert request.task is ModelTask.PDF_EXTRACT
    assert request.idempotency_key == "correlation-1"
    assert request.input == {"document_ref": "doc-1"}
    with pytest.raises(TypeError):
        request.input["document_ref"] = "changed"  # type: ignore[index]


def test_model_response_requires_schema_and_profile_provenance() -> None:
    response = ModelResponse(
        task=ModelTask.PDF_EXTRACT,
        model="extractor-v1",
        response_schema="pdf-extraction-v1",
        output={"artifact_ref": "artifact-1"},
        source_version="sha256:abc",
    )

    assert response.output == {"artifact_ref": "artifact-1"}
    assert response.source_version == "sha256:abc"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"model": "", "task": ModelTask.EMBED, "input": {}, "metadata": {}, "response_schema": "v1"},
        {"model": "embed-v1", "task": ModelTask.EMBED, "input": [], "metadata": {}, "response_schema": "v1"},
        {"model": "embed-v1", "task": ModelTask.EMBED, "input": {}, "metadata": {}, "response_schema": ""},
        {"model": "embed-v1", "task": ModelTask.EMBED, "input": {}, "metadata": {}, "response_schema": "v1", "idempotency_key": " "},
    ],
)
def test_model_request_rejects_invalid_boundary_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ModelValidationError):
        ModelRequest(**kwargs)  # type: ignore[arg-type]


def test_model_client_protocol_is_async_and_fake_can_return_validated_response() -> None:
    class FakeModelClient:
        async def invoke(self, request: ModelRequest) -> ModelResponse:
            return ModelResponse(
                task=request.task,
                model=request.model,
                response_schema=request.response_schema,
                output={"ok": True},
                source_version="sha256:abc",
            )

    async def verify() -> None:
        request = ModelRequest(
            model="answer-v1",
            task=ModelTask.ANSWER_GENERATE,
            input={"question": "What is rhythm?"},
            metadata={"document_ref": "doc-1"},
            response_schema="answer-v1",
        )
        response = await FakeModelClient().invoke(request)
        assert response.task is ModelTask.ANSWER_GENERATE
        assert response.output == {"ok": True}

    asyncio.run(verify())
