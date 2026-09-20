"""FastAPI composition root for the Saxophone backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Final

import httpx
from fastapi import FastAPI

from saxophone.app.settings import AppSettings
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
    http_client: httpx.AsyncClient | None = None


@dataclass(frozen=True, slots=True)
class AppOverrides:
    """Explicit test-only substitutions for infrastructure ports."""

    remote_gpu_gateway: RemoteGpuGateway | None = None


def create_app(
    settings: AppSettings,
    *,
    overrides: AppOverrides | None = None,
) -> FastAPI:
    """Compose the sole ASGI application without reading process environment."""

    resolved_overrides = overrides or AppOverrides()
    http_client: httpx.AsyncClient | None = None
    remote_gpu_gateway = resolved_overrides.remote_gpu_gateway
    if remote_gpu_gateway is None:
        http_client = httpx.AsyncClient()
        remote_gpu_gateway = HttpRemoteGpuGateway(settings, http_client=http_client)

    container = AppContainer(
        settings=settings,
        remote_gpu_gateway=remote_gpu_gateway,
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
    async def health() -> dict[str, str]:
        remote_gpu = await container.remote_gpu_gateway.health()
        return {
            "app": "ready",
            "remote_gpu": remote_gpu.status,
            **_DISABLED_CAPABILITIES,
        }

    return app
