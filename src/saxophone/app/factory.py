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
from saxophone.extraction.ports import PdfExtractor
from saxophone.extraction.remote import RemotePdfExtractor
from saxophone.platform.artifacts import LocalArtifactRepository
from saxophone.platform.model_client import LiteLLMModelClient, ModelClient
from saxophone.platform.remote_gpu import (
    HttpRemoteGpuGateway,
    RemoteGpuGateway,
)
from saxophone.retrieval.use_cases import RetrieveEvidence
from saxophone.interfaces.api import build_capability_router
from saxophone.workflows.process_document import ProcessDocument


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
    artifact_repository: ArtifactRepository | None = None
    process_document: ProcessDocument | None = None


@dataclass(frozen=True, slots=True)
class AppOverrides:
    """Explicit test-only substitutions for infrastructure ports."""

    remote_gpu_gateway: RemoteGpuGateway | None = None
    model_client: ModelClient | None = None
    retrieve_evidence: RetrieveEvidence | None = None
    answer_question: AnswerQuestion | None = None
    pdf_extractor: PdfExtractor | None = None
    artifact_repository: ArtifactRepository | None = None
    process_document: ProcessDocument | None = None


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
        http_client = httpx.AsyncClient()
    if remote_gpu_gateway is None:
        remote_gpu_gateway = HttpRemoteGpuGateway(settings, http_client=http_client)
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

    artifact_repository = resolved_overrides.artifact_repository
    if artifact_repository is None:
        artifact_repository = LocalArtifactRepository(settings.data_root / "artifacts")
    process_document = resolved_overrides.process_document
    if process_document is None:
        process_document = ProcessDocument(artifact_repository, pdf_extractor)

    container = AppContainer(
        settings=settings,
        remote_gpu_gateway=remote_gpu_gateway,
        model_client=model_client,
        http_client=http_client,
        retrieve_evidence=resolved_overrides.retrieve_evidence,
        answer_question=resolved_overrides.answer_question,
        pdf_extractor=pdf_extractor,
        artifact_repository=artifact_repository,
        process_document=process_document,
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
        ),
    )

    @app.get("/api/v1/health")
    async def health() -> dict[str, object]:
        remote_gpu = await container.remote_gpu_gateway.health()
        return {
            "app": "ready",
            "remote_gpu": remote_gpu.status,
            "remote_gpu_capabilities": list(remote_gpu.capabilities),
            "extraction": (
                "ready"
                if container.pdf_extractor is not None
                else _DISABLED_CAPABILITIES["extraction"]
            ),
            "ingestion": _DISABLED_CAPABILITIES["ingestion"],
            "retrieval": "ready" if container.retrieve_evidence is not None else "disabled",
            "chat": "ready" if container.answer_question is not None else "disabled",
        }

    return app
