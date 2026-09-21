"""FastAPI composition root for the Saxophone backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
import re
from typing import AsyncIterator
from uuid import uuid4

import httpx
import anyio
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import Response

from saxophone.app.settings import AppSettings
from saxophone.chat import AnswerGenerator, AnswerQuestion, ImageArtifactGate
from saxophone.documents import ArtifactRepository, ImageArtifactResolver, KnowledgeRepository
from saxophone.extraction import (
    PdfExtractor,
    RemotePdfExtractor,
    RepositoryExtractionArtifactPayloadProvider,
)
from saxophone.ingestion.adapters import FileEmbeddingReuseStore, RemoteEmbeddingProvider
from saxophone.ingestion import (
    EmbeddingProvider,
    EmbeddingReuseStore,
    IngestDocument,
    IndexDocument,
    VectorIndex,
)
from saxophone.platform.artifacts import (
    LocalArtifactRepository,
    RepositoryBackedImageArtifactGate,
)
from saxophone.platform.chroma import create_chroma_vector_index
from saxophone.platform.concurrency import create_blocking_io_limiter
from saxophone.platform.knowledge import JsonKnowledgeRepository
from saxophone.platform.model_client import LiteLLMModelClient, ModelClient
from saxophone.platform.observability import EventMetrics, EventSink, LoggingEventSink
from saxophone.platform.remote_gpu import (
    CachedRemoteGpuGateway,
    HttpRemoteGpuGateway,
    RemoteGpuGateway,
)
from saxophone.retrieval import ChunkRetriever, RetrieveEvidence
from saxophone.tagging import (
    JsonTagCatalogRepository,
    JsonTaggedParagraphRepository,
    RemoteParagraphTagger,
    RemoteTagConflictResolver,
    TagAndPersistParagraph,
    TagCatalogRepository,
    TagConflictResolver,
    TagGenerator,
    TagParagraph,
    TaggedParagraphRepository,
)
from saxophone.interfaces.api import build_capability_router
from saxophone.interfaces.pdf_layout_web import app as pdf_layout_app
from saxophone.workflows import (
    IngestExtractedDocument,
    ProcessAndPersistDocument,
    ProcessDocument,
)


def _capability_status(*, configured: bool, model_service_status: str) -> str:
    """Expose wiring and model-service readiness as one safe capability state."""

    if not configured:
        return "disabled"
    if model_service_status == "ready":
        return "ready"
    return "degraded"


_CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _correlation_id_from_request(request: Request) -> str:
    candidate = request.headers.get("X-Correlation-ID", "").strip()
    if _CORRELATION_ID_PATTERN.fullmatch(candidate):
        return candidate
    return str(uuid4())


@dataclass(frozen=True, slots=True)
class AppContainer:
    """Explicit dependencies owned by one application instance."""

    settings: AppSettings
    remote_gpu_gateway: RemoteGpuGateway
    model_client: ModelClient
    event_sink: EventSink
    metrics: EventMetrics | None = None
    http_client: httpx.AsyncClient | None = None
    retrieve_evidence: RetrieveEvidence | None = None
    answer_question: AnswerQuestion | None = None
    pdf_extractor: PdfExtractor | None = None
    embedding_provider: EmbeddingProvider | None = None
    embedding_reuse: EmbeddingReuseStore | None = None
    vector_index: VectorIndex | None = None
    artifact_repository: ArtifactRepository | None = None
    image_artifact_resolver: ImageArtifactResolver | None = None
    image_artifact_gate: ImageArtifactGate | None = None
    process_document: ProcessDocument | None = None
    process_and_persist_document: ProcessAndPersistDocument | None = None
    index_document: IndexDocument | None = None
    ingest_extracted_document: IngestExtractedDocument | None = None
    tagged_paragraph_repository: TaggedParagraphRepository | None = None
    tag_catalog_repository: TagCatalogRepository | None = None
    tag_generator: TagGenerator | None = None
    tag_conflict_resolver: TagConflictResolver | None = None
    knowledge_repository: KnowledgeRepository | None = None


@dataclass(frozen=True, slots=True)
class AppOverrides:
    """Explicit test-only substitutions for infrastructure ports."""

    remote_gpu_gateway: RemoteGpuGateway | None = None
    model_client: ModelClient | None = None
    event_sink: EventSink | None = None
    retrieve_evidence: RetrieveEvidence | None = None
    answer_question: AnswerQuestion | None = None
    retriever: ChunkRetriever | None = None
    answer_generator: AnswerGenerator | None = None
    image_artifact_gate: ImageArtifactGate | None = None
    pdf_extractor: PdfExtractor | None = None
    embedding_provider: EmbeddingProvider | None = None
    embedding_reuse: EmbeddingReuseStore | None = None
    artifact_repository: ArtifactRepository | None = None
    image_artifact_resolver: ImageArtifactResolver | None = None
    process_document: ProcessDocument | None = None
    process_and_persist_document: ProcessAndPersistDocument | None = None
    vector_index: VectorIndex | None = None
    disable_vector_index: bool = False
    index_document: IndexDocument | None = None
    ingest_extracted_document: IngestExtractedDocument | None = None
    tagged_paragraph_repository: TaggedParagraphRepository | None = None
    tag_catalog_repository: TagCatalogRepository | None = None
    tag_generator: TagGenerator | None = None
    tag_conflict_resolver: TagConflictResolver | None = None
    knowledge_repository: KnowledgeRepository | None = None


def create_layout_app() -> FastAPI:
    """Compose PDF layout mode without general model-service dependencies."""
    app = FastAPI(title="Saxophone PDF Layout")
    app.mount("/pdf-layout", pdf_layout_app)
    return app


def create_app(
    settings: AppSettings,
    *,
    overrides: AppOverrides | None = None,
) -> FastAPI:
    """Compose the sole ASGI application without reading process environment."""

    resolved_overrides = overrides or AppOverrides()
    io_limiter = create_blocking_io_limiter()
    http_client: httpx.AsyncClient | None = None
    remote_gpu_gateway = resolved_overrides.remote_gpu_gateway
    model_client = resolved_overrides.model_client
    event_sink = resolved_overrides.event_sink or LoggingEventSink()
    metrics = event_sink.metrics if isinstance(event_sink, LoggingEventSink) else None
    if metrics is None and resolved_overrides.event_sink is None:
        metrics = EventMetrics()
        event_sink = LoggingEventSink(metrics=metrics)
    if remote_gpu_gateway is None or model_client is None:
        http_client = httpx.AsyncClient(verify=settings.remote_gpu_tls_verify)
    if remote_gpu_gateway is None:
        remote_gpu_gateway = HttpRemoteGpuGateway(
            settings,
            http_client=http_client,
            timeout_seconds=settings.remote_gpu_health_timeout_seconds,
        )
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
            retry_jitter_ratio=settings.litellm_retry_jitter_ratio,
            circuit_breaker_failure_threshold=settings.litellm_circuit_breaker_failure_threshold,
            circuit_breaker_cooldown_seconds=settings.litellm_circuit_breaker_cooldown_seconds,
            event_sink=event_sink,
            metrics=metrics,
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
        artifact_repository = LocalArtifactRepository(
            settings.data_root / "artifacts",
            io_limiter=io_limiter,
        )
    image_artifact_gate = resolved_overrides.image_artifact_gate
    if image_artifact_gate is None and resolved_overrides.image_artifact_resolver is not None:
        image_artifact_gate = RepositoryBackedImageArtifactGate(
            artifact_repository,
            resolved_overrides.image_artifact_resolver,
            io_limiter=io_limiter,
        )
    tagged_paragraph_repository = resolved_overrides.tagged_paragraph_repository
    if tagged_paragraph_repository is None:
        tagged_paragraph_repository = JsonTaggedParagraphRepository(
            settings.data_root / "tagged-paragraphs",
            io_limiter=io_limiter,
        )
    tag_catalog_repository = resolved_overrides.tag_catalog_repository
    if tag_catalog_repository is None:
        tag_catalog_repository = JsonTagCatalogRepository(
            settings.data_root / "tag-catalog.json",
            io_limiter=io_limiter,
        )
    knowledge_repository = resolved_overrides.knowledge_repository
    if knowledge_repository is None:
        knowledge_repository = JsonKnowledgeRepository(
            settings.data_root / "knowledge",
            io_limiter=io_limiter,
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
        embedding_reuse = FileEmbeddingReuseStore(
            settings.data_root / "embedding-reuse.json",
            io_limiter=io_limiter,
        )
    vector_index = resolved_overrides.vector_index
    if vector_index is None and not resolved_overrides.disable_vector_index:
        vector_index = create_chroma_vector_index(settings, io_limiter=io_limiter)
    index_document = resolved_overrides.index_document
    if index_document is None and vector_index is not None:
        index_document = IndexDocument(
            vector_index,
            embedding_provider,
            embedding_reuse,
            knowledge_repository=knowledge_repository,
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

    retrieve_evidence = resolved_overrides.retrieve_evidence
    if retrieve_evidence is None and resolved_overrides.retriever is not None:
        retrieve_evidence = RetrieveEvidence(resolved_overrides.retriever)
    answer_question = resolved_overrides.answer_question
    if answer_question is None and retrieve_evidence is not None:
        if resolved_overrides.answer_generator is not None:
            answer_question = AnswerQuestion(
                retrieve_evidence,
                resolved_overrides.answer_generator,
                resolved_overrides.image_artifact_gate,
            )

    container = AppContainer(
        settings=settings,
        remote_gpu_gateway=remote_gpu_gateway,
        model_client=model_client,
        event_sink=event_sink,
        metrics=metrics,
        http_client=http_client,
        retrieve_evidence=retrieve_evidence,
        answer_question=answer_question,
        pdf_extractor=pdf_extractor,
        embedding_provider=embedding_provider,
        embedding_reuse=embedding_reuse,
        vector_index=vector_index,
        artifact_repository=artifact_repository,
        image_artifact_resolver=resolved_overrides.image_artifact_resolver,
        image_artifact_gate=image_artifact_gate,
        process_document=process_document,
        process_and_persist_document=process_and_persist_document,
        index_document=index_document,
        ingest_extracted_document=ingest_extracted_document,
        tagged_paragraph_repository=tagged_paragraph_repository,
        tag_catalog_repository=tag_catalog_repository,
        tag_generator=tag_generator,
        tag_conflict_resolver=tag_conflict_resolver,
        knowledge_repository=knowledge_repository,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            try:
                if vector_index is not None:
                    aclose = getattr(vector_index, "aclose", None)
                    if callable(aclose):
                        await aclose()
                    else:
                        close = getattr(vector_index, "close", None)
                        if callable(close):
                            await anyio.to_thread.run_sync(close, limiter=io_limiter)
            finally:
                if http_client is not None:
                    await http_client.aclose()

    app = FastAPI(title="Saxophone RAG backend", lifespan=lifespan)

    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next) -> Response:
        correlation_id = _correlation_id_from_request(request)
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    app.state.container = container
    app.include_router(
        build_capability_router(
            retrieve_evidence=container.retrieve_evidence,
            answer_question=container.answer_question,
            pdf_extractor=container.pdf_extractor,
            process_workflow=container.process_document,
            process_and_persist_workflow=container.process_and_persist_document,
            artifact_repository=container.artifact_repository,
            image_artifact_resolver=container.image_artifact_resolver,
            image_artifact_gate=container.image_artifact_gate,
            index_document=container.index_document,
            ingest_extracted_document=container.ingest_extracted_document,
            max_upload_bytes=settings.max_upload_bytes,
        ),
    )
    app.mount("/pdf-layout", pdf_layout_app)

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
            "extraction": _capability_status(
                configured=container.pdf_extractor is not None,
                model_service_status=remote_gpu.status,
            ),
            "ingestion": _capability_status(
                configured=container.index_document is not None,
                model_service_status=remote_gpu.status,
            ),
            "retrieval": _capability_status(
                configured=container.retrieve_evidence is not None,
                model_service_status=remote_gpu.status,
            ),
            "chat": _capability_status(
                configured=container.answer_question is not None,
                model_service_status=remote_gpu.status,
            ),
        }

    @app.get("/api/v1/metrics")
    async def metrics() -> dict[str, object]:
        """Expose only the immutable, provider-independent metrics snapshot."""

        if container.metrics is None:
            return {"status": "disabled", "snapshot": None}
        return {"status": "ready", "snapshot": asdict(container.metrics.snapshot())}

    return app
