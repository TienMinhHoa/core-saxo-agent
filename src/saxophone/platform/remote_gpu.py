"""Contracts for the remote GPU boundary.

The first Phase 1 slice deliberately provides only a lifecycle-safe local
fallback.  The HTTP submit/poll adapter belongs behind this contract in a
later slice, so importing or composing the app cannot start GPU work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from saxophone.app.settings import AppSettings


RemoteGpuStatus = Literal["ready", "degraded", "unavailable"]


@dataclass(frozen=True, slots=True)
class RemoteGpuHealth:
    """The public, non-sensitive health result of the remote GPU service."""

    status: RemoteGpuStatus


class RemoteGpuGateway(Protocol):
    """Port used by application services that need remote GPU capabilities."""

    async def health(self) -> RemoteGpuHealth:
        """Return the latest safe-to-publish remote service status."""


class UnavailableRemoteGpuGateway:
    """Safe Phase 1 default until an HTTP gateway is wired at startup."""

    async def health(self) -> RemoteGpuHealth:
        return RemoteGpuHealth(status="unavailable")


class HttpRemoteGpuGateway:
    """HTTP implementation of the remote GPU health port.

    The application owns the lifecycle of the injected shared client.  This
    adapter only performs a single authenticated capability-health request and
    converts every transport or contract failure into the safe public state.
    """

    def __init__(
        self,
        settings: AppSettings,
        *,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._health_url = f"{settings.remote_gpu_base_url.rstrip('/')}/v1/health"
        self._http_client = http_client
        self._headers = {"Authorization": f"Bearer {settings.remote_gpu_bearer_token}"}

    async def health(self) -> RemoteGpuHealth:
        try:
            response = await self._http_client.get(
                self._health_url,
                headers=self._headers,
            )
            response.raise_for_status()
            payload = response.json()
            status = payload.get("status") if isinstance(payload, dict) else None
            if status in {"ready", "degraded", "unavailable"}:
                return RemoteGpuHealth(status=status)
        except (httpx.HTTPError, TypeError, ValueError):
            pass
        return RemoteGpuHealth(status="unavailable")
