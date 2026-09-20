"""FastAPI composition root for the Saxophone backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Final

import httpx
from fastapi import FastAPI

from saxophone.app.settings import AppSettings
from saxophone.platform.model_client import LiteLLMModelClient, ModelClient
from saxophone.platform.remote_gpu import (
    HttpRemoteGpuGateway,
    RemoteGpuGateway,
)


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


@dataclass(frozen=True, slots=True)
class AppOverrides:
    """Explicit test-only substitutions for infrastructure ports."""

    remote_gpu_gateway: RemoteGpuGateway | None = None
    model_client: ModelClient | None = None


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

    container = AppContainer(
        settings=settings,
        remote_gpu_gateway=remote_gpu_gateway,
        model_client=model_client,
        http_client=http_client,
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

    @app.get("/api/v1/health")
    async def health() -> dict[str, object]:
        remote_gpu = await container.remote_gpu_gateway.health()
        return {
            "app": "ready",
            "remote_gpu": remote_gpu.status,
            "remote_gpu_capabilities": list(remote_gpu.capabilities),
            **_DISABLED_CAPABILITIES,
        }

    return app
