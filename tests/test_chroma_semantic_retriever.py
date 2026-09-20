from __future__ import annotations

import pytest

from saxophone.retrieval.adapters import ChromaSemanticRetriever


class _EmbeddingProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        assert texts == ["find scales"]
        return [[0.1, 0.2]]


class _Collection:
    def query(self, **kwargs: object) -> dict[str, list[list[object]]]:
        assert kwargs["query_embeddings"] == [[0.1, 0.2]]
        assert kwargs["n_results"] == 2
        assert kwargs["where"] == {"access_scope": "public"}
        assert kwargs["include"] == ["documents", "metadatas", "distances"]
        return {
            "ids": [["chunk-2", "chunk-1"]],
            "documents": [["second", "first"]],
            "metadatas": [[{"page": 2}, {"page": 1}]],
            "distances": [[0.1, 0.4]],
        }


class _MalformedCollection:
    def __init__(self, result: object) -> None:
        self._result = result

    def query(self, **kwargs: object) -> object:
        return self._result


@pytest.mark.parametrize("retrieval_version", [" chroma-v1", "chroma-v1 ", "cafe\u0301"])
def test_chroma_retriever_rejects_non_canonical_retrieval_version(
    retrieval_version: str,
) -> None:
    with pytest.raises(ValueError, match="retrieval_version.*canonical"):
        ChromaSemanticRetriever(_Collection(), _EmbeddingProvider(), retrieval_version=retrieval_version)


@pytest.mark.parametrize("retrieval_version", [True, 0, object()])
def test_chroma_retriever_rejects_non_string_retrieval_version(
    retrieval_version: object,
) -> None:
    with pytest.raises(ValueError, match="retrieval_version"):
        ChromaSemanticRetriever(  # type: ignore[arg-type]
            _Collection(), _EmbeddingProvider(), retrieval_version=retrieval_version
        )


@pytest.mark.anyio
async def test_chroma_retriever_maps_results_to_ranked_provider_independent_hits() -> None:
    retriever = ChromaSemanticRetriever(
        _Collection(), _EmbeddingProvider(), retrieval_version="chroma-v1"
    )

    hits = await retriever.search(
        "find scales", filters={"access_scope": "public"}, limit=2
    )

    assert [hit.chunk_ref for hit in hits] == ["chunk-2", "chunk-1"]
    assert [hit.rank for hit in hits] == [1, 2]
    assert hits[0].semantic_score == pytest.approx(0.9)
    assert hits[0].metadata == {"page": 2, "document": "second"}


@pytest.mark.anyio
async def test_chroma_retriever_returns_empty_for_non_positive_limit_without_io() -> None:
    class _FailIfCalled:
        def embed(self, texts: list[str]) -> list[list[float]]:
            raise AssertionError("embedding should not be called")

    retriever = ChromaSemanticRetriever(_FailIfCalled(), _FailIfCalled())

    assert await retriever.search("ignored", limit=0) == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "result",
    [
        {"ids": ["chunk-1"]},
        {"ids": [["chunk-1"]], "documents": [["text"]], "metadatas": [[{}]]},
        {
            "ids": [["chunk-1"]],
            "documents": [["text"]],
            "metadatas": [[{}]],
            "distances": [[float("nan")]],
        },
    ],
)
async def test_chroma_retriever_rejects_malformed_provider_results(result: object) -> None:
    retriever = ChromaSemanticRetriever(
        _MalformedCollection(result), _EmbeddingProvider(), retrieval_version="chroma-v1"
    )

    with pytest.raises(ValueError, match="Chroma result"):
        await retriever.search("find scales")


@pytest.mark.anyio
@pytest.mark.parametrize("chunk_id", ["", "  ", 42, True])
async def test_chroma_retriever_rejects_invalid_chunk_ids(chunk_id: object) -> None:
    result = {
        "ids": [[chunk_id]],
        "documents": [["text"]],
        "metadatas": [[{}]],
        "distances": [[0.1]],
    }
    retriever = ChromaSemanticRetriever(
        _MalformedCollection(result), _EmbeddingProvider(), retrieval_version="chroma-v1"
    )

    with pytest.raises(ValueError, match="Chroma result chunk ids"):
        await retriever.search("find scales")
