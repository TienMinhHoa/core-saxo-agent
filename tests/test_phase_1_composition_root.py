from __future__ import annotations

import importlib
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from saxophone.app.factory import AppContainer, AppOverrides, create_app
from saxophone.app.settings import AppSettings
from saxophone.chat.models import GeneratedAnswer
from saxophone.chat.service import AnswerQuestion
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.use_cases import RetrieveEvidence
from saxophone.platform.remote_gpu import HttpRemoteGpuGateway, RemoteGpuHealth
from saxophone.platform.model_client import LiteLLMModelClient
from saxophone.platform.observability import EventMetrics, LoggingEventSink
from saxophone.extraction.remote import RemotePdfExtractor
from saxophone.extraction.persistence import RepositoryExtractionArtifactPayloadProvider
from saxophone.ingestion.adapters import FileEmbeddingReuseStore, RemoteEmbeddingProvider
from saxophone.ingestion.adapters import ChromaVectorIndex
from saxophone.platform.knowledge import JsonKnowledgeRepository
from saxophone.platform.chroma import create_chroma_vector_index
from saxophone.tagging.persistence import (
    JsonTagCatalogRepository,
    JsonTaggedParagraphRepository,
)


VALID_ENVIRONMENT = {
    "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
    "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token-must-not-leak",
}


class FakeRemoteGpuGateway:
    def __init__(self, status: str) -> None:
        self.status = status
        self.health_requests = 0

    async def health(self) -> RemoteGpuHealth:
        self.health_requests += 1
        return RemoteGpuHealth(status=self.status, capabilities=("embed",))


class FakeModelClient:
    async def invoke(self, request):
        raise AssertionError("composition test must not invoke the model")


class FakePdfExtractor:
    async def extract(self, request):
        raise AssertionError("composition test must not invoke extraction")


class FakeRetriever:
    async def search(self, query, *, filters=None, limit=10):
        return [
            ChunkHit(
                "document-1",
                "chunk-1",
                1,
                "retrieval-test-v1",
                {"document": "validated source text"},
            )
        ]


class FakeAnswerGenerator:
    async def generate(self, question, evidence):
        return GeneratedAnswer("answer", "model-v1", {}, 0.0)


def build_settings() -> AppSettings:
    return AppSettings.from_environment(VALID_ENVIRONMENT)


def test_runtime_modules_import_without_reading_environment_or_starting_provider(
    monkeypatch,
) -> None:
    def reject_environment_access(*_args, **_kwargs):
        raise AssertionError("runtime module must not read process environment at import time")

    monkeypatch.setattr("os.getenv", reject_environment_access)
    monkeypatch.setattr("os.environ.get", reject_environment_access)

    assert importlib.import_module("saxophone.main")
    assert importlib.import_module("saxophone.app.factory")


def test_create_app_composes_fastapi_and_exposes_container() -> None:
    gateway = FakeRemoteGpuGateway(status="ready")
    model_client = FakeModelClient()

    app = create_app(
        build_settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=gateway,
            model_client=model_client,
        ),
    )

    assert isinstance(app, FastAPI)
    assert isinstance(app.state.container, AppContainer)
    assert app.state.container.settings == build_settings()
    assert app.state.container.remote_gpu_gateway is gateway
    assert app.state.container.model_client is model_client


def test_default_composition_owns_one_http_client_and_closes_it_with_lifespan() -> None:
    """The production gateway must not leak a client after ASGI shutdown."""
    app = create_app(build_settings())
    container = app.state.container

    assert isinstance(container.remote_gpu_gateway, HttpRemoteGpuGateway)
    assert isinstance(container.model_client, LiteLLMModelClient)
    assert isinstance(container.http_client, httpx.AsyncClient)
    assert not container.http_client.is_closed

    with TestClient(app):
        assert not container.http_client.is_closed

    assert container.http_client.is_closed


def test_default_composition_applies_remote_gpu_tls_verification_setting(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class SpyAsyncClient:
        def __init__(self, **kwargs) -> None:
            calls.append(kwargs)
            self.is_closed = False

        async def post(self, *args, **kwargs):
            raise AssertionError("composition test must not perform model I/O")

        async def get(self, *args, **kwargs):
            raise AssertionError("composition test must not perform health I/O")

        async def aclose(self) -> None:
            self.is_closed = True

    monkeypatch.setattr("saxophone.app.factory.httpx.AsyncClient", SpyAsyncClient)
    settings = AppSettings.from_environment({
        **VALID_ENVIRONMENT,
        "SAXO_REMOTE_GPU_TLS_VERIFY": "false",
    })

    create_app(settings)

    assert calls == [{"verify": False}]


def test_default_composition_uses_litellm_settings_for_model_client() -> None:
    settings = AppSettings.from_environment({
        **VALID_ENVIRONMENT,
        "SAXO_LITELLM_ENDPOINT": "https://llm.example.test/v1/chat",
        "SAXO_LITELLM_TIMEOUT_SECONDS": "12.5",
        "SAXO_LITELLM_MAX_ATTEMPTS": "3",
        "SAXO_LITELLM_RETRY_BACKOFF_SECONDS": "0.25",
        "SAXO_LITELLM_RETRY_JITTER_RATIO": "0.2",
        "SAXO_LITELLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD": "5",
        "SAXO_LITELLM_CIRCUIT_BREAKER_COOLDOWN_SECONDS": "45.5",
    })

    app = create_app(settings)
    client = app.state.container.model_client

    assert isinstance(client, LiteLLMModelClient)
    assert client.endpoint == "https://llm.example.test/v1/chat"
    assert client.timeout_seconds == 12.5
    assert client.max_attempts == 3
    assert client.retry_backoff_seconds == 0.25
    assert client.retry_jitter_ratio == 0.2
    assert client.circuit_breaker_failure_threshold == 5
    assert client.circuit_breaker_cooldown_seconds == 45.5


def test_default_composition_wires_structured_logging_sink_to_model_client() -> None:
    app = create_app(build_settings())

    container = app.state.container

    assert isinstance(container.event_sink, LoggingEventSink)
    assert isinstance(container.metrics, EventMetrics)
    assert container.event_sink.metrics is container.metrics
    assert container.model_client._event_sink is container.event_sink


def test_default_composition_wires_remote_pdf_extractor_to_shared_model_client() -> None:
    app = create_app(build_settings())

    extractor = app.state.container.pdf_extractor

    assert isinstance(extractor, RemotePdfExtractor)
    assert extractor.model == build_settings().litellm_model_profile


def test_composition_builds_retrieval_and_chat_from_application_ports() -> None:
    retriever = FakeRetriever()
    answer_generator = FakeAnswerGenerator()

    app = create_app(
        build_settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(status="ready"),
            model_client=FakeModelClient(),
            retriever=retriever,
            answer_generator=answer_generator,
        ),
    )

    container = app.state.container
    assert isinstance(container.retrieve_evidence, RetrieveEvidence)
    assert isinstance(container.answer_question, AnswerQuestion)
    assert TestClient(app).get("/api/v1/health").json()["retrieval"] == "ready"
    assert TestClient(app).get("/api/v1/health").json()["chat"] == "ready"


def test_default_composition_wires_extraction_persistence_workflow() -> None:
    app = create_app(build_settings())

    container = app.state.container

    assert container.process_and_persist_document is not None
    assert isinstance(
        container.process_and_persist_document._payloads,
        RepositoryExtractionArtifactPayloadProvider,
    )


def test_default_composition_wires_remote_embedding_provider_to_shared_model_client() -> None:
    app = create_app(build_settings())

    provider = app.state.container.embedding_provider

    assert isinstance(provider, RemoteEmbeddingProvider)
    assert provider.model == build_settings().litellm_model_profile


def test_default_composition_wires_durable_embedding_reuse_store() -> None:
    app = create_app(build_settings())

    reuse_store = app.state.container.embedding_reuse

    assert isinstance(reuse_store, FileEmbeddingReuseStore)
    assert reuse_store.path == (build_settings().data_root / "embedding-reuse.json")


def test_default_composition_wires_durable_knowledge_repository_into_indexing() -> None:
    app = create_app(build_settings())

    container = app.state.container

    assert isinstance(container.knowledge_repository, JsonKnowledgeRepository)
    assert container.knowledge_repository._io_limiter is container.artifact_repository._io_limiter
    assert container.index_document is not None
    assert container.index_document._knowledge_repository is container.knowledge_repository


def test_default_composition_builds_persistent_chroma_vector_index(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class FakeCollection:
        metadata = {"embedding_dimension": 1536, "schema_version": "saxo-chunk-v1"}

    class FakeClient:
        def __init__(self, *, path: str) -> None:
            calls.append(("client", path))

        def close(self) -> None:
            calls.append(("close",))

        def get_or_create_collection(self, *, name: str, metadata: dict[str, object]):
            calls.append(("collection", name, metadata))
            return FakeCollection()

    class FakeChroma:
        PersistentClient = FakeClient

    monkeypatch.setitem(__import__("sys").modules, "chromadb", FakeChroma)

    settings = AppSettings.from_environment({
        **VALID_ENVIRONMENT,
        "SAXO_CHROMA_PERSIST_DIRECTORY": "D:/saxo-data/chroma",
        "SAXO_CHROMA_COLLECTION_NAME": "music_chunks_v2",
    })

    app = create_app(settings)

    assert isinstance(app.state.container.vector_index, ChromaVectorIndex)
    assert calls == [
        ("client", str(settings.chroma_persist_directory)),
        (
            "collection",
            settings.chroma_collection_name,
            {"embedding_dimension": settings.embedding_dimension, "schema_version": "saxo-chunk-v1"},
        ),
    ]


def test_default_composition_rejects_existing_chroma_dimension_mismatch(monkeypatch) -> None:
    class FakeCollection:
        metadata = {"embedding_dimension": 768, "schema_version": "saxo-chunk-v1"}

    class FakeClient:
        def __init__(self, *, path: str) -> None:
            pass

        def get_or_create_collection(self, *, name: str, metadata: dict[str, object]):
            return FakeCollection()

    class FakeChroma:
        PersistentClient = FakeClient

    monkeypatch.setitem(__import__("sys").modules, "chromadb", FakeChroma)

    settings = AppSettings.from_environment(VALID_ENVIRONMENT)

    with pytest.raises(ValueError, match="embedding dimension"):
        create_app(settings)


def test_chroma_client_is_closed_when_collection_metadata_validation_fails(monkeypatch) -> None:
    class FakeCollection:
        metadata = {"embedding_dimension": 768, "schema_version": "saxo-chunk-v1"}

    clients: list[object] = []

    class FakeClient:
        def __init__(self, *, path: str) -> None:
            self.closed = False
            clients.append(self)

        def get_or_create_collection(self, *, name: str, metadata: dict[str, object]):
            return FakeCollection()

        def close(self) -> None:
            self.closed = True

    class FakeChroma:
        PersistentClient = FakeClient

    monkeypatch.setitem(__import__("sys").modules, "chromadb", FakeChroma)

    with pytest.raises(ValueError, match="embedding dimension"):
        create_chroma_vector_index(AppSettings.from_environment(VALID_ENVIRONMENT))

    assert len(clients) == 1
    assert clients[0].closed is True


def test_chroma_client_is_closed_when_collection_creation_fails(monkeypatch) -> None:
    clients: list[object] = []

    class FakeClient:
        def __init__(self, *, path: str) -> None:
            self.closed = False
            clients.append(self)

        def get_or_create_collection(self, *, name: str, metadata: dict[str, object]):
            raise RuntimeError("collection creation failed")

        def close(self) -> None:
            self.closed = True

    class FakeChroma:
        PersistentClient = FakeClient

    monkeypatch.setitem(__import__("sys").modules, "chromadb", FakeChroma)

    with pytest.raises(RuntimeError, match="collection creation failed"):
        create_chroma_vector_index(AppSettings.from_environment(VALID_ENVIRONMENT))

    assert len(clients) == 1
    assert clients[0].closed is True


def test_chroma_client_is_closed_when_vector_index_construction_fails(monkeypatch) -> None:
    class FakeCollection:
        metadata = {"embedding_dimension": 1536, "schema_version": "saxo-chunk-v1"}

    clients: list[object] = []

    class FakeClient:
        def __init__(self, *, path: str) -> None:
            self.closed = False
            clients.append(self)

        def get_or_create_collection(self, *, name: str, metadata: dict[str, object]):
            return FakeCollection()

        def close(self) -> None:
            self.closed = True

    class FakeChroma:
        PersistentClient = FakeClient

    class FailingVectorIndex:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("vector index construction failed")

    monkeypatch.setitem(__import__("sys").modules, "chromadb", FakeChroma)
    monkeypatch.setattr("saxophone.platform.chroma.ChromaVectorIndex", FailingVectorIndex)

    with pytest.raises(RuntimeError, match="vector index construction failed"):
        create_chroma_vector_index(AppSettings.from_environment(VALID_ENVIRONMENT))

    assert len(clients) == 1
    assert clients[0].closed is True


def test_default_composition_rejects_non_mapping_chroma_metadata(monkeypatch) -> None:
    class FakeCollection:
        metadata = ["not-a-metadata-mapping"]

    class FakeClient:
        def __init__(self, *, path: str) -> None:
            pass

        def get_or_create_collection(self, *, name: str, metadata: dict[str, object]):
            return FakeCollection()

    class FakeChroma:
        PersistentClient = FakeClient

    monkeypatch.setitem(__import__("sys").modules, "chromadb", FakeChroma)

    with pytest.raises(ValueError, match="metadata"):
        create_app(build_settings())


def test_default_composition_rejects_boolean_chroma_dimension(monkeypatch) -> None:
    class FakeCollection:
        metadata = {"embedding_dimension": True, "schema_version": "saxo-chunk-v1"}

    class FakeClient:
        def __init__(self, *, path: str) -> None:
            pass

        def get_or_create_collection(self, *, name: str, metadata: dict[str, object]):
            return FakeCollection()

    class FakeChroma:
        PersistentClient = FakeClient

    monkeypatch.setitem(__import__("sys").modules, "chromadb", FakeChroma)

    settings = AppSettings.from_environment({**VALID_ENVIRONMENT, "SAXO_EMBEDDING_DIMENSION": "1"})

    with pytest.raises(ValueError, match="embedding dimension"):
        create_app(settings)


@pytest.mark.parametrize("schema_version", [True, 1, "", "  "])
def test_default_composition_rejects_malformed_chroma_schema_version(
    monkeypatch, schema_version: object
) -> None:
    class FakeCollection:
        metadata = {"embedding_dimension": 1536, "schema_version": schema_version}

    class FakeClient:
        def __init__(self, *, path: str) -> None:
            pass

        def get_or_create_collection(self, *, name: str, metadata: dict[str, object]):
            return FakeCollection()

    class FakeChroma:
        PersistentClient = FakeClient

    monkeypatch.setitem(__import__("sys").modules, "chromadb", FakeChroma)

    with pytest.raises(ValueError, match="schema version"):
        create_app(build_settings())


def test_default_composition_closes_persistent_chroma_client_on_shutdown(monkeypatch) -> None:
    class FakeCollection:
        metadata = {"embedding_dimension": 1536, "schema_version": "saxo-chunk-v1"}

    class FakeClient:
        def __init__(self, *, path: str) -> None:
            pass

        def get_or_create_collection(self, *, name: str, metadata: dict[str, object]):
            return FakeCollection()

        def close(self) -> None:
            raise AssertionError("synchronous Chroma close must not run on the event loop")

    class FakeChroma:
        PersistentClient = FakeClient

    monkeypatch.setitem(__import__("sys").modules, "chromadb", FakeChroma)
    app = create_app(build_settings())
    client = app.state.container.vector_index._client
    aclose_calls: list[object] = []

    async def tracked_aclose(index) -> None:
        aclose_calls.append(index)

    monkeypatch.setattr(ChromaVectorIndex, "aclose", tracked_aclose)

    with TestClient(app):
        assert aclose_calls == []

    assert aclose_calls == [app.state.container.vector_index]
    assert client is app.state.container.vector_index._client


def test_lifespan_closes_shared_http_client_when_vector_cleanup_fails(monkeypatch) -> None:
    class SpyAsyncClient:
        def __init__(self, **kwargs) -> None:
            self.is_closed = False

        async def post(self, *args, **kwargs):
            raise AssertionError("shutdown test must not perform model I/O")

        async def get(self, *args, **kwargs):
            raise AssertionError("shutdown test must not perform health I/O")

        async def aclose(self) -> None:
            self.is_closed = True

    class FailingVectorIndex:
        async def aclose(self) -> None:
            raise RuntimeError("vector cleanup failed")

    monkeypatch.setattr("saxophone.app.factory.httpx.AsyncClient", SpyAsyncClient)
    app = create_app(
        build_settings(),
        overrides=AppOverrides(
            vector_index=FailingVectorIndex(),
        ),
    )
    client = app.state.container.http_client
    assert client is not None

    with pytest.raises(RuntimeError, match="vector cleanup failed"):
        with TestClient(app):
            pass

    assert client.is_closed is True


def test_lifespan_offloads_sync_vector_cleanup_to_bounded_worker(monkeypatch) -> None:
    calls: list[tuple[object, object]] = []

    async def tracked_run_sync(callable_, *, limiter):
        calls.append((callable_, limiter))
        callable_()

    monkeypatch.setattr("saxophone.app.factory.anyio.to_thread.run_sync", tracked_run_sync)

    class SyncVectorIndex:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    vector_index = SyncVectorIndex()
    app = create_app(
        build_settings(),
        overrides=AppOverrides(vector_index=vector_index),
    )

    with TestClient(app):
        pass

    assert vector_index.closed is True
    assert len(calls) == 1
    assert calls[0][0].__self__ is vector_index


def test_indexing_composition_uses_durable_reuse_store_by_default() -> None:
    vector_index = object()
    app = create_app(
        build_settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(status="ready"),
            model_client=FakeModelClient(),
            vector_index=vector_index,
        ),
    )

    container = app.state.container

    assert isinstance(container.embedding_reuse, FileEmbeddingReuseStore)
    assert container.index_document is not None
    assert container.vector_index is vector_index
    assert container.embedding_reuse.path == (
        build_settings().data_root / "embedding-reuse.json"
    )


def test_embedding_provider_override_is_kept_in_container() -> None:
    provider = RemoteEmbeddingProvider(FakeModelClient(), model="test-embedding")
    app = create_app(
        build_settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(status="ready"),
            model_client=FakeModelClient(),
            embedding_provider=provider,
        ),
    )

    assert app.state.container.embedding_provider is provider


def test_default_composition_wires_tag_persistence_under_data_root() -> None:
    app = create_app(build_settings())

    container = app.state.container

    assert isinstance(container.tagged_paragraph_repository, JsonTaggedParagraphRepository)
    assert isinstance(container.tag_catalog_repository, JsonTagCatalogRepository)
    assert container.tagged_paragraph_repository.root == (
        build_settings().data_root / "tagged-paragraphs"
    ).resolve()
    assert container.tag_catalog_repository.path == (
        build_settings().data_root / "tag-catalog.json"
    ).resolve()
    assert container.embedding_reuse is not None
    assert container.tagged_paragraph_repository._io_limiter is container.embedding_reuse._io_limiter
    assert container.tag_catalog_repository._io_limiter is container.embedding_reuse._io_limiter


def test_tag_persistence_overrides_are_kept_in_container() -> None:
    paragraph_repository = JsonTaggedParagraphRepository(Path("test-paragraphs"))
    catalog_repository = JsonTagCatalogRepository(Path("test-tags.json"))
    app = create_app(
        build_settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(status="ready"),
            model_client=FakeModelClient(),
            tagged_paragraph_repository=paragraph_repository,
            tag_catalog_repository=catalog_repository,
        ),
    )

    assert app.state.container.tagged_paragraph_repository is paragraph_repository
    assert app.state.container.tag_catalog_repository is catalog_repository


def test_extraction_override_is_kept_in_container_and_marks_health_ready() -> None:
    extractor = FakePdfExtractor()
    app = create_app(
        build_settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(status="ready"),
            model_client=FakeModelClient(),
            pdf_extractor=extractor,
        ),
    )

    assert app.state.container.pdf_extractor is extractor
    assert TestClient(app).get("/api/v1/health").json()["extraction"] == "ready"


def test_health_uses_override_and_returns_stable_disabled_capabilities() -> None:
    gateway = FakeRemoteGpuGateway(status="degraded")
    app = create_app(
        build_settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=gateway,
            model_client=FakeModelClient(),
        ),
    )

    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "app": "ready",
        "model_service": "degraded",
        "remote_gpu": "degraded",
        "remote_gpu_capabilities": ["embed"],
        "extraction": "degraded",
        "ingestion": "degraded",
        "retrieval": "disabled",
        "chat": "disabled",
    }
    assert gateway.health_requests == 1


def test_health_preserves_unavailable_remote_gpu_status() -> None:
    gateway = FakeRemoteGpuGateway(status="unavailable")
    app = create_app(
        build_settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=gateway,
            model_client=FakeModelClient(),
        ),
    )

    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["remote_gpu"] == "unavailable"


def test_health_does_not_disclose_connection_secrets_or_local_paths() -> None:
    gateway = FakeRemoteGpuGateway(status="ready")
    app = create_app(
        build_settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=gateway,
            model_client=FakeModelClient(),
        ),
    )

    response = TestClient(app).get("/api/v1/health")

    body = response.text
    assert VALID_ENVIRONMENT["SAXO_REMOTE_GPU_BEARER_TOKEN"] not in body
    assert build_settings().remote_gpu_base_url not in body
    assert str(build_settings().data_root) not in body
