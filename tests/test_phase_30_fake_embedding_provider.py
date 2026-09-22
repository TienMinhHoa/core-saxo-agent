from __future__ import annotations

import pytest

from saxophone.ingestion.adapters import FakeEmbeddingProvider
from saxophone.ingestion.models import EmbeddingRecord


@pytest.mark.anyio
async def test_fake_embedding_provider_returns_configured_vectors_in_request_order() -> None:
    provider = FakeEmbeddingProvider(
        {"chunk-1": (0.1, 0.2), "chunk-2": (0.3, 0.4)},
        model="fake-embedding",
    )

    records = await provider.embed(
        [("chunk-2", "second"), ("chunk-1", "first")], source_version="v1"
    )

    assert records == (
        EmbeddingRecord("chunk-2", "v1", "fake-embedding", (0.3, 0.4)),
        EmbeddingRecord("chunk-1", "v1", "fake-embedding", (0.1, 0.2)),
    )


@pytest.mark.anyio
async def test_fake_embedding_provider_rejects_missing_vector_and_duplicate_input() -> None:
    provider = FakeEmbeddingProvider({"chunk-1": (0.1,)})

    with pytest.raises(ValueError, match="missing vector"):
        await provider.embed([("chunk-2", "text")], source_version="v1")

    with pytest.raises(ValueError, match="unique"):
        await provider.embed(
            [("chunk-1", "one"), ("chunk-1", "two")], source_version="v1"
        )


@pytest.mark.anyio
async def test_fake_embedding_provider_rejects_invalid_vectors() -> None:
    with pytest.raises(ValueError, match="finite"):
        FakeEmbeddingProvider({"chunk-1": (float("nan"),)})
