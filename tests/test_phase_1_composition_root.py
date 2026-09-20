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
from saxophone.extraction.remote import RemotePdfExtractor
from saxophone.extraction.persistence import RepositoryExtractionArtifactPayloadProvider
from saxophone.ingestion.adapters import FileEmbeddingReuseStore, RemoteEmbeddingProvider
from saxophone.ingestion.adapters import ChromaVectorIndex
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
    })

    app = create_app(settings)
    client = app.state.container.model_client

    assert isinstance(client, LiteLLMModelClient)
    assert client.endpoint == "https://llm.example.test/v1/chat"
    assert client.timeout_seconds == 12.5
    assert client.max_attempts == 3
    assert client.retry_backoff_seconds == 0.25


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


def test_default_composition_builds_persistent_chroma_vector_index(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class FakeCollection:
        metadata = {"embedding_dimension": 1536, "schema_version": "saxo-chunk-v1"}

    class FakeClient:
        def __init__(self, *, path: str) -> None:
            calls.append(("client", path))

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
        "extraction": "ready",
            "ingestion": "ready",
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
