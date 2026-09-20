"""FastAPI composition root for the Saxophone backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fastapi import FastAPI

from saxophone.app.settings import AppSettings
from saxophone.platform.remote_gpu import (
    RemoteGpuGateway,
    UnavailableRemoteGpuGateway,
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
    container = AppContainer(
        settings=settings,
        remote_gpu_gateway=(
            resolved_overrides.remote_gpu_gateway or UnavailableRemoteGpuGateway()
        ),
    )
    app = FastAPI(title="Saxophone RAG backend")
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
