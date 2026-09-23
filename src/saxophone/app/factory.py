"""FastAPI composition root for the Saxophone backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
import re
import sys
from typing import AsyncIterator
from uuid import uuid4

import httpx
import anyio
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import Response

from saxophone.app.settings import AppSettings
from saxophone.chat import (
    AnswerGenerator,
    AnswerQuestion,
    GroundedAnswerService,
    ImageArtifactGate,
)
from saxophone.documents import ArtifactRepository, ImageArtifactResolver, KnowledgeRepository
from saxophone.extraction import (
    PdfExtractor,
    RemotePdfExtractor,
    RepositoryExtractionArtifactPayloadProvider,
)
from saxophone.ingestion.adapters import FileEmbeddingReuseStore, RemoteEmbeddingProvider
from saxophone.ingestion.concept_embedding import ConceptCatalogVectorPreparationService
from saxophone.ingestion.concept_repository import SqliteConceptCatalogRepository
from saxophone.ingestion.content_ledger import SqliteContentLedger
from saxophone.ingestion import (
    EmbeddingProvider,
    EmbeddingReuseStore,
    DocumentIngestionService,
    DocumentChunkTaggingService,
    IngestDocument,
    IndexDocument,
    VectorIndex,
)
from saxophone.ingestion.state import SqliteIngestionStateRepository
from saxophone.ingestion.transaction import SqliteIngestionTransactionRepository
from saxophone.ingestion.vector_state import SqliteVectorIndexStateRepository
from saxophone.ingestion.vector_sync import VectorSyncService
from saxophone.platform.artifacts import (
    LocalArtifactRepository,
    RepositoryBackedImageArtifactGate,
)
from saxophone.platform.chroma import create_chroma_vector_index
from saxophone.platform.concurrency import create_blocking_io_limiter
from saxophone.platform.knowledge import JsonKnowledgeRepository
from saxophone.platform.direct_model_client import DirectApiModelClient
from saxophone.platform.model_client import LiteLLMModelClient, ModelClient
from saxophone.platform.observability import (
    DailyTextFileEventSink,
    EventMetrics,
    EventSink,
    LoggingEventSink,
)
from saxophone.platform.remote_gpu import (
    CachedRemoteGpuGateway,
    DirectProviderHealthGateway,
    HttpRemoteGpuGateway,
    RemoteGpuGateway,
)
from saxophone.retrieval import ChunkRetriever, QuestionRetrievalService, RetrieveEvidence
from saxophone.retrieval.adapters import VectorIndexChunkRetriever
from saxophone.retrieval.role_selection import StructuredConceptRoleSelector
from saxophone.retrieval.sqlite_context import SqliteRetrievalContextRepository
from saxophone.services.extract_topic import (
    DocumentIngestionFacadeAdapter,
    DocumentTaggingFacadeAdapter,
    ExtractTopicService,
)
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
    ChunkTagger,
)
from saxophone.tagging.chunk_service import ChunkTaggingService, ChunkTaggingTransactionService
from saxophone.tagging.structured_chunk import StructuredChunkTagger
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository
from saxophone.tagging.structured_provider import (
    RemoteStructuredLlmProvider,
    StructuredLlmProvider,
    StructuredOutputMode,
)
from saxophone.interfaces.api import build_agent_chat_router, build_capability_router
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


def _supports_vector_sync(vector_index: object | None) -> bool:
    """Check the minimal publication port needed by the ingestion coordinator."""

    return vector_index is not None and all(
        callable(getattr(vector_index, method, None))
        for method in ("upsert_chunks", "delete_chunks")
    )


def _supports_topic_retrieval(
    vector_index: object | None,
    embedding_provider: object | None,
) -> bool:
    return (
        vector_index is not None
        and embedding_provider is not None
        and callable(getattr(vector_index, "search", None))
        and callable(getattr(embedding_provider, "embed_texts", None))
    )


def _create_direct_model_client(
    settings: AppSettings,
    *,
    http_client: httpx.AsyncClient,
    deepseek_model: str,
    event_sink: EventSink,
    metrics: EventMetrics | None,
) -> DirectApiModelClient:
    assert settings.deepseek_api_key is not None
    assert settings.openai_api_key is not None
    return DirectApiModelClient(
        http_client=http_client,
        deepseek_api_base_url=settings.deepseek_api_base_url,
        deepseek_api_key=settings.deepseek_api_key,
        deepseek_model=deepseek_model,
        deepseek_reasoning_effort=settings.deepseek_reasoning_effort,
        deepseek_max_tokens=settings.deepseek_max_tokens,
        openai_api_base_url=settings.openai_api_base_url,
        openai_api_key=settings.openai_api_key,
        openai_embedding_model=settings.openai_embedding_model,
        embedding_dimension=settings.embedding_dimension,
        timeout_seconds=settings.litellm_timeout_seconds,
        max_attempts=settings.litellm_max_attempts,
        retry_backoff_seconds=settings.litellm_retry_backoff_seconds,
        event_sink=event_sink,
        metrics=metrics,
    )


@dataclass(frozen=True, slots=True)
class AppContainer:
    """Explicit dependencies owned by one application instance."""

    settings: AppSettings
    remote_gpu_gateway: RemoteGpuGateway
    model_client: ModelClient
    structured_llm_provider: StructuredLlmProvider
    agent_structured_llm_provider: StructuredLlmProvider
    event_sink: EventSink
    metrics: EventMetrics | None = None
    http_client: httpx.AsyncClient | None = None
    retrieve_evidence: RetrieveEvidence | None = None
    answer_question: AnswerQuestion | None = None
    pdf_extractor: PdfExtractor | None = None
    embedding_provider: EmbeddingProvider | None = None
    embedding_reuse: EmbeddingReuseStore | None = None
    content_ledger: SqliteContentLedger | None = None
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
    chunk_tagger: ChunkTagger | None = None
    chunk_tagging: DocumentChunkTaggingService | None = None
    ingestion_transaction_repository: SqliteIngestionTransactionRepository | None = None
    concept_catalog_repository: SqliteConceptCatalogRepository | None = None
    document_ingestion: DocumentIngestionService | None = None
    question_retrieval: QuestionRetrievalService | None = None
    grounded_answer: GroundedAnswerService | None = None
    agent_chat: GroundedAnswerService | None = None
    extract_topic: ExtractTopicService | None = None


@dataclass(frozen=True, slots=True)
class AppOverrides:
    """Explicit test-only substitutions for infrastructure ports."""

    remote_gpu_gateway: RemoteGpuGateway | None = None
    model_client: ModelClient | None = None
    structured_llm_provider: StructuredLlmProvider | None = None
    agent_structured_llm_provider: StructuredLlmProvider | None = None
    event_sink: EventSink | None = None
    retrieve_evidence: RetrieveEvidence | None = None
    answer_question: AnswerQuestion | None = None
    retriever: ChunkRetriever | None = None
    answer_generator: AnswerGenerator | None = None
    image_artifact_gate: ImageArtifactGate | None = None
    pdf_extractor: PdfExtractor | None = None
    embedding_provider: EmbeddingProvider | None = None
    embedding_reuse: EmbeddingReuseStore | None = None
    content_ledger: SqliteContentLedger | None = None
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
    chunk_tagger: ChunkTagger | None = None
    document_ingestion: DocumentIngestionService | None = None
    agent_chat: GroundedAnswerService | None = None


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
    direct_provider = settings.model_provider == "direct"
    io_limiter = create_blocking_io_limiter()
    http_client: httpx.AsyncClient | None = None
    remote_gpu_gateway = resolved_overrides.remote_gpu_gateway
    model_client = resolved_overrides.model_client
    if resolved_overrides.event_sink is None:
        metrics = EventMetrics()
        event_sink = DailyTextFileEventSink(
            Path("logs"),
            metrics=metrics,
            progress_stream=sys.stdout,
        )
    else:
        event_sink = resolved_overrides.event_sink
        metrics = event_sink.metrics if isinstance(event_sink, LoggingEventSink) else None
    if remote_gpu_gateway is None or model_client is None:
        http_client = httpx.AsyncClient(verify=settings.remote_gpu_tls_verify)
    if remote_gpu_gateway is None:
        if direct_provider:
            assert settings.deepseek_api_key is not None
            assert settings.openai_api_key is not None
            remote_gpu_gateway = DirectProviderHealthGateway(
                http_client=http_client,
                deepseek_api_base_url=settings.deepseek_api_base_url,
                deepseek_api_key=settings.deepseek_api_key,
                openai_api_base_url=settings.openai_api_base_url,
                openai_api_key=settings.openai_api_key,
                timeout_seconds=settings.remote_gpu_health_timeout_seconds,
            )
        else:
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
        if direct_provider:
            model_client = _create_direct_model_client(
                settings,
                http_client=http_client,
                deepseek_model=settings.deepseek_model,
                event_sink=event_sink,
                metrics=metrics,
            )
        else:
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
    structured_llm_provider = resolved_overrides.structured_llm_provider
    if structured_llm_provider is None:
        structured_llm_provider = RemoteStructuredLlmProvider(
            model_client,
            model=settings.litellm_model_profile,
            mode=StructuredOutputMode(settings.litellm_structured_output_mode),
        )
    agent_structured_llm_provider = resolved_overrides.agent_structured_llm_provider
    if agent_structured_llm_provider is None:
        agent_model_client = model_client
        if direct_provider and resolved_overrides.model_client is None:
            agent_model_client = _create_direct_model_client(
                settings,
                http_client=http_client,
                deepseek_model=settings.agent_chat_model,
                event_sink=event_sink,
                metrics=metrics,
            )
        agent_structured_llm_provider = RemoteStructuredLlmProvider(
            agent_model_client,
            model=settings.agent_chat_model,
            mode=StructuredOutputMode(settings.litellm_structured_output_mode),
        )

    pdf_extractor = resolved_overrides.pdf_extractor
    if pdf_extractor is None and not direct_provider:
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
    ingestion_database = settings.data_root / "ingestion.sqlite3"
    content_ledger = resolved_overrides.content_ledger
    if content_ledger is None and settings.chunk_tagging_enabled:
        content_ledger = SqliteContentLedger(ingestion_database)
    embedding_reuse = resolved_overrides.embedding_reuse
    if embedding_reuse is None:
        embedding_reuse = content_ledger or FileEmbeddingReuseStore(
            settings.data_root / "embedding-reuse.json", io_limiter=io_limiter
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
    chunk_tagger: ChunkTagger | None = None
    chunk_tagging: DocumentChunkTaggingService | None = None
    ingestion_transaction_repository: SqliteIngestionTransactionRepository | None = None
    concept_catalog_repository: SqliteConceptCatalogRepository | None = None
    vector_state: SqliteVectorIndexStateRepository | None = None
    document_ingestion = resolved_overrides.document_ingestion
    if settings.chunk_tagging_enabled:
        chunk_tagger = resolved_overrides.chunk_tagger or StructuredChunkTagger(
            structured_llm_provider
        )
        ingestion_transaction_repository = SqliteIngestionTransactionRepository(
            ingestion_database
        )
        concept_catalog_repository = SqliteConceptCatalogRepository(ingestion_database)
        vector_state = SqliteVectorIndexStateRepository(ingestion_database)
        chunk_tagging = DocumentChunkTaggingService(
            ChunkTaggingTransactionService(
                ChunkTaggingService(chunk_tagger),
                ingestion_transaction_repository,
            ),
            content_ledger=content_ledger,
        )
    ingest_extracted_document = resolved_overrides.ingest_extracted_document
    if ingest_extracted_document is None and index_document is not None:
        if chunk_tagging is not None:
            ingest_workflow = IngestDocument(
                None,
                index_document,
                chunk_tagging=chunk_tagging,
                vector_state=vector_state,
                concept_catalog_repository=concept_catalog_repository,
                concept_vector_preparation=ConceptCatalogVectorPreparationService(
                    embedding_provider
                ),
            )
        else:
            tag_and_persist = TagAndPersistParagraph(
                TagParagraph(tag_generator, tag_conflict_resolver),
                tagged_paragraph_repository,
                tag_catalog_repository,
            )
            ingest_workflow = IngestDocument(tag_and_persist, index_document)
        if (
            document_ingestion is None
            and chunk_tagging is not None
            and _supports_vector_sync(vector_index)
        ):
            assert ingestion_transaction_repository is not None
            outbox = SqliteVectorOutboxRepository(ingestion_database)
            lifecycle = SqliteIngestionStateRepository(ingestion_database)
            assert vector_state is not None
            vector_sync = VectorSyncService(
                outbox,
                vector_index,
                state=vector_state,
            )
            document_ingestion = DocumentIngestionService(
                ingest_workflow,
                vector_sync=vector_sync,
                lifecycle=lifecycle,
                event_sink=event_sink,
            )
        ingest_extracted_document = IngestExtractedDocument(
            artifact_repository,
            index_document,
            ingest_document=ingest_workflow,
            document_ingestion=document_ingestion,
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

    question_retrieval: QuestionRetrievalService | None = None
    grounded_answer: GroundedAnswerService | None = None
    agent_chat = resolved_overrides.agent_chat
    extract_topic: ExtractTopicService | None = None
    if (
        chunk_tagging is not None
        and document_ingestion is not None
        and ingestion_transaction_repository is not None
        and _supports_topic_retrieval(vector_index, embedding_provider)
    ):
        question_retrieval = QuestionRetrievalService(
            retriever=VectorIndexChunkRetriever(embedding_provider, vector_index),
            selector=StructuredConceptRoleSelector(structured_llm_provider),
            context_repository=SqliteRetrievalContextRepository(ingestion_database),
        )
        grounded_answer = GroundedAnswerService(
            retrieval=question_retrieval,
            provider=structured_llm_provider,
            model_version=settings.litellm_model_profile,
        )
        if agent_chat is None:
            agent_chat = GroundedAnswerService(
                retrieval=question_retrieval,
                provider=agent_structured_llm_provider,
                model_version=settings.agent_chat_model,
            )
        extract_topic = ExtractTopicService(
            ingestion=DocumentIngestionFacadeAdapter(document_ingestion),
            tagging=DocumentTaggingFacadeAdapter(chunk_tagging),
            retrieval=question_retrieval,
            answering=grounded_answer,
        )

    container = AppContainer(
        settings=settings,
        remote_gpu_gateway=remote_gpu_gateway,
        model_client=model_client,
        structured_llm_provider=structured_llm_provider,
        agent_structured_llm_provider=agent_structured_llm_provider,
        event_sink=event_sink,
        metrics=metrics,
        http_client=http_client,
        retrieve_evidence=retrieve_evidence,
        answer_question=answer_question,
        pdf_extractor=pdf_extractor,
        embedding_provider=embedding_provider,
        embedding_reuse=embedding_reuse,
        content_ledger=content_ledger,
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
        chunk_tagger=chunk_tagger,
        chunk_tagging=chunk_tagging,
        ingestion_transaction_repository=ingestion_transaction_repository,
        concept_catalog_repository=concept_catalog_repository,
        document_ingestion=document_ingestion,
        question_retrieval=question_retrieval,
        grounded_answer=grounded_answer,
        agent_chat=agent_chat,
        extract_topic=extract_topic,
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
    app.include_router(build_agent_chat_router(agent_chat=container.agent_chat))
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
