from __future__ import annotations

import pytest

from saxophone.ingestion.adapters import RemoteEmbeddingProvider
from saxophone.ingestion.models import EmbeddingRecord
from saxophone.platform.model_client import ModelTask, ModelValidationError


class FakeModelClient:
    def __init__(self, response):
        self.response = response
        self.request = None

    async def invoke(self, request):
        self.request = request
        return self.response


def _response(output):
    from saxophone.platform.model_client import ModelResponse

    return ModelResponse(
        task=ModelTask.EMBED,
        model="embed-model",
        response_schema="embedding-v1",
        output=output,
        source_version="source-v1",
    )


@pytest.mark.anyio
async def test_remote_embedding_provider_maps_validated_vectors() -> None:
    client = FakeModelClient(
        _response({"embeddings": [{"chunk_id": "chunk-1", "vector": [0.1, 0.2]}]})
    )

    records = await RemoteEmbeddingProvider(client, model="embed-model").embed(
        [("chunk-1", "A phrase")], source_version="source-v1"
    )

    assert records == (
        EmbeddingRecord("chunk-1", "source-v1", "embed-model", (0.1, 0.2)),
    )
    assert client.request.task is ModelTask.EMBED
    assert client.request.input["texts"] == [{"chunk_id": "chunk-1", "text": "A phrase"}]


@pytest.mark.anyio
async def test_remote_embedding_provider_rejects_wrong_task_or_shape() -> None:
    client = FakeModelClient(
        _response({"embeddings": [{"chunk_id": "chunk-1", "vector": [0.1]}]})
    )
    client.response = _response({"embeddings": [{"chunk_id": "chunk-1"}]})

    with pytest.raises(ModelValidationError, match="vector"):
        await RemoteEmbeddingProvider(client, model="embed-model").embed(
            [("chunk-1", "A phrase")], source_version="source-v1"
        )


@pytest.mark.anyio
async def test_remote_embedding_provider_rejects_missing_or_extra_chunk() -> None:
    client = FakeModelClient(
        _response(
            {
                "embeddings": [
                    {"chunk_id": "chunk-1", "vector": [0.1]},
                    {"chunk_id": "chunk-2", "vector": [0.2]},
                ]
            }
        )
    )

    with pytest.raises(ModelValidationError, match="chunk"):
        await RemoteEmbeddingProvider(client, model="embed-model").embed(
            [("chunk-1", "A phrase")], source_version="source-v1"
        )
