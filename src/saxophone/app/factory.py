"""FastAPI composition root for the Saxophone backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Final

import httpx
from fastapi import FastAPI

from saxophone.app.settings import AppSettings
from saxophone.chat.service import AnswerQuestion
from saxophone.documents.ports import ArtifactRepository
from saxophone.extraction.persistence import RepositoryExtractionArtifactPayloadProvider
from saxophone.extraction.ports import PdfExtractor
from saxophone.extraction.remote import RemotePdfExtractor
from saxophone.ingestion.adapters import FileEmbeddingReuseStore, RemoteEmbeddingProvider
from saxophone.ingestion.ports import EmbeddingProvider, EmbeddingReuseStore, VectorIndex
from saxophone.ingestion.use_cases import IngestDocument, IndexDocument
from saxophone.platform.artifacts import LocalArtifactRepository
from saxophone.platform.model_client import LiteLLMModelClient, ModelClient
from saxophone.platform.remote_gpu import (
    CachedRemoteGpuGateway,
    HttpRemoteGpuGateway,
    RemoteGpuGateway,
)
from saxophone.retrieval.use_cases import RetrieveEvidence
from saxophone.tagging.persistence import JsonTagCatalogRepository, JsonTaggedParagraphRepository
from saxophone.tagging.adapters import RemoteParagraphTagger, RemoteTagConflictResolver
from saxophone.tagging.ports import TagCatalogRepository, TagConflictResolver, TagGenerator, TaggedParagraphRepository
from saxophone.tagging.use_cases import TagAndPersistParagraph, TagParagraph
from saxophone.interfaces.api import build_capability_router
from saxophone.workflows.process_document import ProcessAndPersistDocument, ProcessDocument
from saxophone.workflows.ingest_extracted_document import IngestExtractedDocument


_DISABLED_CAPABILITIES: Final = {
    "extraction": "disabled",
    "ingestion": "disabled",
    "retrieval": "disabled",
    "chat": "disabled",
}


@dataclass(frozen=True, slots=True)
class AppContainer:
    """Explicit dependencies owned by one application instance."""

    settings: AppSettings
    remote_gpu_gateway: RemoteGpuGateway
    model_client: ModelClient
    http_client: httpx.AsyncClient | None = None
    retrieve_evidence: RetrieveEvidence | None = None
    answer_question: AnswerQuestion | None = None
    pdf_extractor: PdfExtractor | None = None
    embedding_provider: EmbeddingProvider | None = None
    embedding_reuse: EmbeddingReuseStore | None = None
    artifact_repository: ArtifactRepository | None = None
    process_document: ProcessDocument | None = None
    process_and_persist_document: ProcessAndPersistDocument | None = None
    index_document: IndexDocument | None = None
    ingest_extracted_document: IngestExtractedDocument | None = None
    tagged_paragraph_repository: TaggedParagraphRepository | None = None
    tag_catalog_repository: TagCatalogRepository | None = None
    tag_generator: TagGenerator | None = None
    tag_conflict_resolver: TagConflictResolver | None = None


@dataclass(frozen=True, slots=True)
class AppOverrides:
    """Explicit test-only substitutions for infrastructure ports."""

    remote_gpu_gateway: RemoteGpuGateway | None = None
    model_client: ModelClient | None = None
    retrieve_evidence: RetrieveEvidence | None = None
    answer_question: AnswerQuestion | None = None
    pdf_extractor: PdfExtractor | None = None
    embedding_provider: EmbeddingProvider | None = None
    embedding_reuse: EmbeddingReuseStore | None = None
    artifact_repository: ArtifactRepository | None = None
    process_document: ProcessDocument | None = None
    process_and_persist_document: ProcessAndPersistDocument | None = None
    vector_index: VectorIndex | None = None
    index_document: IndexDocument | None = None
    ingest_extracted_document: IngestExtractedDocument | None = None
    tagged_paragraph_repository: TaggedParagraphRepository | None = None
    tag_catalog_repository: TagCatalogRepository | None = None
    tag_generator: TagGenerator | None = None
    tag_conflict_resolver: TagConflictResolver | None = None


def create_app(
    settings: AppSettings,
    *,
    overrides: AppOverrides | None = None,
) -> FastAPI:
    """Compose the sole ASGI application without reading process environment."""

    resolved_overrides = overrides or AppOverrides()
    http_client: httpx.AsyncClient | None = None
    remote_gpu_gateway = resolved_overrides.remote_gpu_gateway
    model_client = resolved_overrides.model_client
    if remote_gpu_gateway is None or model_client is None:
        http_client = httpx.AsyncClient(verify=settings.remote_gpu_tls_verify)
    if remote_gpu_gateway is None:
        remote_gpu_gateway = HttpRemoteGpuGateway(settings, http_client=http_client)
    cached_remote_gpu_gateway = CachedRemoteGpuGateway(
        remote_gpu_gateway,
        ttl_seconds=settings.remote_gpu_health_cache_seconds,
    )
    if model_client is None:
        model_client = LiteLLMModelClient(
            settings.litellm_endpoint,
            http_client=http_client,
            bearer_token=settings.remote_gpu_bearer_token,
            timeout_seconds=settings.litellm_timeout_seconds,
            max_attempts=settings.litellm_max_attempts,
            retry_backoff_seconds=settings.litellm_retry_backoff_seconds,
        )

    pdf_extractor = resolved_overrides.pdf_extractor
    if pdf_extractor is None:
        pdf_extractor = RemotePdfExtractor(
            model_client,
            model=settings.litellm_model_profile,
        )

    embedding_provider = resolved_overrides.embedding_provider
    if embedding_provider is None:
        embedding_provider = RemoteEmbeddingProvider(
            model_client,
            model=settings.litellm_model_profile,
        )

    artifact_repository = resolved_overrides.artifact_repository
    if artifact_repository is None:
        artifact_repository = LocalArtifactRepository(settings.data_root / "artifacts")
    tagged_paragraph_repository = resolved_overrides.tagged_paragraph_repository
    if tagged_paragraph_repository is None:
        tagged_paragraph_repository = JsonTaggedParagraphRepository(
            settings.data_root / "tagged-paragraphs",
        )
    tag_catalog_repository = resolved_overrides.tag_catalog_repository
    if tag_catalog_repository is None:
        tag_catalog_repository = JsonTagCatalogRepository(
            settings.data_root / "tag-catalog.json",
        )
    tag_generator = resolved_overrides.tag_generator or RemoteParagraphTagger(
        model_client, model=settings.litellm_model_profile,
    )
    tag_conflict_resolver = resolved_overrides.tag_conflict_resolver or RemoteTagConflictResolver(
        model_client, model=settings.litellm_model_profile,
    )
    process_document = resolved_overrides.process_document
    if process_document is None:
        process_document = ProcessDocument(artifact_repository, pdf_extractor)
    process_and_persist_document = resolved_overrides.process_and_persist_document
    if process_and_persist_document is None and resolved_overrides.process_document is None:
        process_and_persist_document = ProcessAndPersistDocument(
            process_document,
            RepositoryExtractionArtifactPayloadProvider(artifact_repository),
            artifact_repository,
        )
    embedding_reuse = resolved_overrides.embedding_reuse
    if embedding_reuse is None:
        embedding_reuse = FileEmbeddingReuseStore(settings.data_root / "embedding-reuse.json")
    index_document = resolved_overrides.index_document
    if index_document is None and resolved_overrides.vector_index is not None:
        index_document = IndexDocument(
            resolved_overrides.vector_index,
            embedding_provider,
            embedding_reuse,
        )
    ingest_extracted_document = resolved_overrides.ingest_extracted_document
    if ingest_extracted_document is None and index_document is not None:
        tag_and_persist = TagAndPersistParagraph(
            TagParagraph(tag_generator, tag_conflict_resolver),
            tagged_paragraph_repository,
            tag_catalog_repository,
        )
        ingest_extracted_document = IngestExtractedDocument(
            artifact_repository,
            index_document,
            ingest_document=IngestDocument(tag_and_persist, index_document),
        )

    container = AppContainer(
        settings=settings,
        remote_gpu_gateway=remote_gpu_gateway,
        model_client=model_client,
        http_client=http_client,
        retrieve_evidence=resolved_overrides.retrieve_evidence,
        answer_question=resolved_overrides.answer_question,
        pdf_extractor=pdf_extractor,
        embedding_provider=embedding_provider,
        embedding_reuse=embedding_reuse,
        artifact_repository=artifact_repository,
        process_document=process_document,
        process_and_persist_document=process_and_persist_document,
        index_document=index_document,
        ingest_extracted_document=ingest_extracted_document,
        tagged_paragraph_repository=tagged_paragraph_repository,
        tag_catalog_repository=tag_catalog_repository,
        tag_generator=tag_generator,
        tag_conflict_resolver=tag_conflict_resolver,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if http_client is not None:
                await http_client.aclose()

    app = FastAPI(title="Saxophone RAG backend", lifespan=lifespan)
    app.state.container = container
    app.include_router(
        build_capability_router(
            retrieve_evidence=container.retrieve_evidence,
            answer_question=container.answer_question,
            pdf_extractor=container.pdf_extractor,
            process_workflow=container.process_document,
            process_and_persist_workflow=container.process_and_persist_document,
            artifact_repository=container.artifact_repository,
            index_document=container.index_document,
            ingest_extracted_document=container.ingest_extracted_document,
        ),
    )

    @app.get("/api/v1/health")
    async def health() -> dict[str, object]:
        remote_gpu = await cached_remote_gpu_gateway.health()
        return {
            "app": "ready",
            # ``model_service`` is the architecture-level name. Keep the
            # older ``remote_gpu`` field during the strangler migration so
            # existing health consumers remain compatible.
            "model_service": remote_gpu.status,
            "remote_gpu": remote_gpu.status,
            "remote_gpu_capabilities": list(remote_gpu.capabilities),
            "extraction": (
                "ready"
                if container.pdf_extractor is not None
                else _DISABLED_CAPABILITIES["extraction"]
            ),
            "ingestion": (
                "ready"
                if container.index_document is not None
                else _DISABLED_CAPABILITIES["ingestion"]
            ),
            "retrieval": "ready" if container.retrieve_evidence is not None else "disabled",
            "chat": "ready" if container.answer_question is not None else "disabled",
        }

    return app
