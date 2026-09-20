"""Contracts for remote model-service capability health.

The health port is intentionally separate from the direct LiteLLM-compatible
request/response client.  It reports service readiness without introducing a
backend-owned submit/poll job lifecycle or starting GPU work during app setup.
"""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import math
import time
from collections.abc import Callable
from typing import Literal, Protocol

import httpx

from saxophone.app.settings import AppSettings


RemoteGpuStatus = Literal["ready", "degraded", "unavailable"]


@dataclass(frozen=True, slots=True)
class RemoteGpuHealth:
    """The public, non-sensitive health result of the remote GPU service."""

    status: RemoteGpuStatus
    capabilities: tuple[str, ...] = ()


class RemoteGpuGateway(Protocol):
    """Port used by application services that need remote GPU capabilities."""

    async def health(self) -> RemoteGpuHealth:
        """Return the latest safe-to-publish remote service status."""


class CachedRemoteGpuGateway:
    """Bound remote health polling while preserving the latest safe result."""

    def __init__(
        self,
        gateway: RemoteGpuGateway,
        *,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be finite and positive")
        if not callable(getattr(gateway, "health", None)):
            raise TypeError("gateway.health must be callable")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._gateway = gateway
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._cached: tuple[float, RemoteGpuHealth] | None = None
        self._lock = asyncio.Lock()

    async def health(self) -> RemoteGpuHealth:
        now = self._clock()
        if self._cached is not None and now - self._cached[0] < self._ttl_seconds:
            return self._cached[1]
        async with self._lock:
            now = self._clock()
            if self._cached is not None and now - self._cached[0] < self._ttl_seconds:
                return self._cached[1]
            health = await self._gateway.health()
            if not isinstance(health, RemoteGpuHealth):
                raise TypeError("gateway.health must return RemoteGpuHealth")
            self._cached = (self._clock(), health)
            return health


class UnavailableRemoteGpuGateway:
    """Safe health result when the external model service is unavailable."""

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
        timeout_seconds: float,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._health_url = f"{settings.remote_gpu_base_url.rstrip('/')}/v1/health"
        self._http_client = http_client
        self._headers = {"Authorization": f"Bearer {settings.remote_gpu_bearer_token}"}
        self._timeout_seconds = timeout_seconds

    async def health(self) -> RemoteGpuHealth:
        try:
            response = await self._http_client.get(
                self._health_url,
                headers=self._headers,
                timeout=self._timeout_seconds,
            )
            if not isinstance(response, httpx.Response):
                raise TypeError("health transport must return an httpx.Response")
            response.raise_for_status()
            payload = response.json()
            status = payload.get("status") if isinstance(payload, dict) else None
            if status in {"ready", "degraded", "unavailable"}:
                return RemoteGpuHealth(
                    status=status,
                    capabilities=_parse_capabilities(payload.get("capabilities")),
                )
        except (httpx.HTTPError, TypeError, ValueError):
            pass
        return RemoteGpuHealth(status="unavailable")


def _parse_capabilities(value: object) -> tuple[str, ...]:
    """Keep only stable, non-sensitive capability names from remote health."""

    if not isinstance(value, list):
        return ()
    capabilities: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized and not any(
            ord(character) < 32 or ord(character) == 127 for character in normalized
        ) and normalized not in capabilities:
            capabilities.append(normalized)
    return tuple(capabilities)
