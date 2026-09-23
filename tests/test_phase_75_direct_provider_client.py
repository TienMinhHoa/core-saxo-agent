from __future__ import annotations

import json

import httpx
import pytest

from saxophone.app.factory import create_app
from saxophone.app.settings import AppSettings, SettingsValidationError
from saxophone.platform.direct_model_client import DirectApiModelClient
from saxophone.platform.model_client import (
    ModelRequest,
    ModelTask,
    ModelValidationError,
)
from saxophone.tagging.structured_provider import StructuredOutputMode


DIRECT_ENVIRONMENT = {
    "SAXO_MODEL_PROVIDER": "direct",
    "DEEPSEEK_API_KEY": "deepseek-secret",
    "OPENAI_API_KEY": "openai-secret",
    "SAXO_CHUNK_TAGGING_ENABLED": "true",
}


def test_direct_provider_settings_use_official_api_defaults() -> None:
    settings = AppSettings.from_environment(DIRECT_ENVIRONMENT)

    assert settings.model_provider == "direct"
    assert settings.deepseek_api_base_url == "https://api.deepseek.com"
    assert settings.deepseek_model == "deepseek-flash"
    assert settings.deepseek_reasoning_effort == "max"
    assert settings.deepseek_max_tokens == 65536
    assert settings.openai_api_base_url == "https://api.openai.com/v1"
    assert settings.openai_embedding_model == "text-embedding-3-small"
    assert settings.embedding_dimension == 1536
    assert settings.litellm_structured_output_mode == "json_object"
    assert "deepseek-secret" not in repr(settings)
    assert "openai-secret" not in repr(settings)


@pytest.mark.parametrize("missing_key", ["DEEPSEEK_API_KEY", "OPENAI_API_KEY"])
def test_direct_provider_settings_require_both_provider_credentials(
    missing_key: str,
) -> None:
    environment = {
        key: value for key, value in DIRECT_ENVIRONMENT.items() if key != missing_key
    }

    with pytest.raises(SettingsValidationError, match=missing_key):
        AppSettings.from_environment(environment)


def test_direct_provider_rejects_native_json_schema_mode() -> None:
    with pytest.raises(
        SettingsValidationError,
        match="SAXO_LITELLM_STRUCTURED_OUTPUT_MODE",
    ):
        AppSettings.from_environment(
            {
                **DIRECT_ENVIRONMENT,
                "SAXO_LITELLM_STRUCTURED_OUTPUT_MODE": "json_schema",
            }
        )


def test_direct_provider_requires_chunk_tagging_flow() -> None:
    with pytest.raises(SettingsValidationError, match="SAXO_CHUNK_TAGGING_ENABLED"):
        AppSettings.from_environment(
            {
                **DIRECT_ENVIRONMENT,
                "SAXO_CHUNK_TAGGING_ENABLED": "false",
            }
        )


@pytest.mark.anyio
async def test_direct_client_maps_embed_task_to_openai_embeddings() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [0.1, 0.2]},
                    {"object": "embedding", "index": 1, "embedding": [0.3, 0.4]},
                ],
                "model": "text-embedding-3-small",
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DirectApiModelClient(
            http_client=http_client,
            deepseek_api_base_url="https://api.deepseek.com",
            deepseek_api_key="deepseek-secret",
            deepseek_model="deepseek-flash",
            deepseek_reasoning_effort="max",
            deepseek_max_tokens=65536,
            openai_api_base_url="https://api.openai.com/v1",
            openai_api_key="openai-secret",
            openai_embedding_model="text-embedding-3-small",
            embedding_dimension=2,
        )
        response = await client.invoke(
            ModelRequest(
                model="saxophone-direct-v1",
                task=ModelTask.EMBED,
                input={
                    "texts": [
                        {"chunk_id": "chunk-1", "text": "Major triad"},
                        {"chunk_id": "chunk-2", "text": "Minor triad"},
                    ]
                },
                metadata={"source_version": "source-v1"},
                response_schema="embedding-v1",
                idempotency_key="embed-source-v1",
            )
        )

    assert response.output == {
        "embeddings": [
            {"chunk_id": "chunk-1", "vector": [0.1, 0.2]},
            {"chunk_id": "chunk-2", "vector": [0.3, 0.4]},
        ]
    }
    assert response.source_version == "source-v1"
    request = requests[0]
    assert request.url == "https://api.openai.com/v1/embeddings"
    assert request.headers["Authorization"] == "Bearer openai-secret"
    assert request.headers["Idempotency-Key"] == "embed-source-v1"
    assert json.loads(request.content) == {
        "model": "text-embedding-3-small",
        "input": ["Major triad", "Minor triad"],
        "dimensions": 2,
        "encoding_format": "float",
    }


@pytest.mark.anyio
async def test_direct_client_maps_structured_task_to_deepseek_thinking_max() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "response-1",
                "model": "deepseek-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "reasoning_content": "private reasoning",
                            "content": json.dumps(
                                {
                                    "answer": "A triad has three notes.",
                                    "used_paragraph_refs": ["paragraph-1"],
                                }
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DirectApiModelClient(
            http_client=http_client,
            deepseek_api_base_url="https://api.deepseek.com",
            deepseek_api_key="deepseek-secret",
            deepseek_model="deepseek-flash",
            deepseek_reasoning_effort="max",
            deepseek_max_tokens=65536,
            openai_api_base_url="https://api.openai.com/v1",
            openai_api_key="openai-secret",
            openai_embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
        )
        response = await client.invoke(
            ModelRequest(
                model="saxophone-direct-v1",
                task=ModelTask.ANSWER_GENERATE,
                input={
                    "system_prompt": "Return JSON grounded in the supplied context.",
                    "user_prompt": "Return exactly one JSON object.",
                    "response_format": "json_object",
                    "schema": {"type": "object"},
                },
                metadata={"source_version": "retrieval-v1"},
                response_schema="structured-answer_generation",
                idempotency_key="answer-1",
            )
        )

    assert response.output == {
        "answer": "A triad has three notes.",
        "used_paragraph_refs": ["paragraph-1"],
    }
    request = requests[0]
    assert request.url == "https://api.deepseek.com/chat/completions"
    assert request.headers["Authorization"] == "Bearer deepseek-secret"
    payload = json.loads(request.content)
    assert payload["model"] == "deepseek-flash"
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "max"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == 65536
    assert payload["stream"] is False
    assert payload["messages"] == [
        {
            "role": "system",
            "content": "Return JSON grounded in the supplied context.",
        },
        {"role": "user", "content": "Return exactly one JSON object."},
    ]
    assert "private reasoning" not in str(response.output)


@pytest.mark.anyio
async def test_direct_client_rejects_wrong_embedding_dimension() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [0.1]}],
                "model": "text-embedding-3-small",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DirectApiModelClient(
            http_client=http_client,
            deepseek_api_base_url="https://api.deepseek.com",
            deepseek_api_key="deepseek-secret",
            deepseek_model="deepseek-flash",
            deepseek_reasoning_effort="max",
            deepseek_max_tokens=65536,
            openai_api_base_url="https://api.openai.com/v1",
            openai_api_key="openai-secret",
            openai_embedding_model="text-embedding-3-small",
            embedding_dimension=2,
        )
        with pytest.raises(ModelValidationError, match="dimension"):
            await client.invoke(
                ModelRequest(
                    model="saxophone-direct-v1",
                    task=ModelTask.EMBED,
                    input={"texts": [{"chunk_id": "chunk-1", "text": "Triad"}]},
                    metadata={"source_version": "source-v1"},
                    response_schema="embedding-v1",
                )
            )


@pytest.mark.anyio
async def test_direct_client_retries_transient_deepseek_failure() -> None:
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"selections": []}'}}
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DirectApiModelClient(
            http_client=http_client,
            deepseek_api_base_url="https://api.deepseek.com",
            deepseek_api_key="deepseek-secret",
            deepseek_model="deepseek-flash",
            deepseek_reasoning_effort="max",
            deepseek_max_tokens=65536,
            openai_api_base_url="https://api.openai.com/v1",
            openai_api_key="openai-secret",
            openai_embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            max_attempts=2,
        )
        response = await client.invoke(
            ModelRequest(
                model="saxophone-direct-v1",
                task=ModelTask.RETRIEVAL_SELECT,
                input={
                    "system_prompt": "Return JSON.",
                    "user_prompt": "Return exactly one JSON object.",
                    "response_format": "json_object",
                    "schema": {"type": "object"},
                },
                metadata={},
                response_schema="structured-concept_role_selection",
                idempotency_key="selection-1",
            )
        )

    assert attempts == 2
    assert response.output == {"selections": []}


@pytest.mark.anyio
async def test_direct_client_rejects_non_json_deepseek_content() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json"}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DirectApiModelClient(
            http_client=http_client,
            deepseek_api_base_url="https://api.deepseek.com",
            deepseek_api_key="deepseek-secret",
            deepseek_model="deepseek-flash",
            deepseek_reasoning_effort="max",
            deepseek_max_tokens=65536,
            openai_api_base_url="https://api.openai.com/v1",
            openai_api_key="openai-secret",
            openai_embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
        )
        with pytest.raises(ModelValidationError, match="valid JSON"):
            await client.invoke(
                ModelRequest(
                    model="saxophone-direct-v1",
                    task=ModelTask.ANSWER_GENERATE,
                    input={
                        "system_prompt": "Return JSON.",
                        "user_prompt": "Return exactly one JSON object.",
                        "response_format": "json_object",
                        "schema": {"type": "object"},
                    },
                    metadata={},
                    response_schema="structured-answer_generation",
                )
            )


def test_direct_provider_composition_wires_direct_clients() -> None:
    settings = AppSettings.from_environment(DIRECT_ENVIRONMENT)
    app = create_app(settings)
    container = app.state.container

    assert isinstance(container.model_client, DirectApiModelClient)
    assert container.structured_llm_provider.structured_output_mode is (
        StructuredOutputMode.JSON_OBJECT
    )
    assert container.pdf_extractor is None
    assert container.extract_topic is not None
