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
from collections.abc import Callable, Mapping
from typing import Literal, Protocol

import httpx

RemoteGpuStatus = Literal["ready", "degraded", "unavailable"]


class RemoteGpuSettings(Protocol):
    """Configuration shape required by the remote health adapter."""

    remote_gpu_base_url: str
    remote_gpu_bearer_token: str


@dataclass(frozen=True, slots=True)
class RemoteGpuHealth:
    """The public, non-sensitive health result of the remote GPU service."""

    status: RemoteGpuStatus
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"ready", "degraded", "unavailable"}:
            raise ValueError("status must be a supported remote health status")
        if (
            not isinstance(self.capabilities, tuple)
            or any(not isinstance(item, str) or not item.strip() for item in self.capabilities)
            or any(
                any(ord(character) < 32 or ord(character) == 127 for character in item)
                for item in self.capabilities
            )
            or len(set(self.capabilities)) != len(self.capabilities)
        ):
            raise ValueError("capabilities must be unique, non-blank, and control-free")


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
        now = self._read_clock()
        if self._cached is not None and now - self._cached[0] < self._ttl_seconds:
            return self._cached[1]
        async with self._lock:
            now = self._read_clock()
            if self._cached is not None and now - self._cached[0] < self._ttl_seconds:
                return self._cached[1]
            health = await self._gateway.health()
            if not isinstance(health, RemoteGpuHealth):
                raise TypeError("gateway.health must return RemoteGpuHealth")
            self._cached = (self._read_clock(), health)
            return health

    def _read_clock(self) -> float:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("clock must return a number")
        if not math.isfinite(value):
            raise ValueError("clock must return a finite number")
        return float(value)


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
        settings: RemoteGpuSettings,
        *,
        http_client: httpx.AsyncClient,
        timeout_seconds: float,
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if not callable(getattr(http_client, "get", None)):
            raise TypeError("http_client.get must be callable")
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


class DirectProviderHealthGateway:
    """Probe direct DeepSeek and OpenAI APIs without billable inference."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        deepseek_api_base_url: str,
        deepseek_api_key: str,
        openai_api_base_url: str,
        openai_api_key: str,
        timeout_seconds: float,
    ) -> None:
        if not callable(getattr(http_client, "get", None)):
            raise TypeError("http_client.get must be callable")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self._http_client = http_client
        self._deepseek_url = _direct_models_url(
            deepseek_api_base_url,
            "deepseek_api_base_url",
        )
        self._openai_url = _direct_models_url(
            openai_api_base_url,
            "openai_api_base_url",
        )
        self._deepseek_headers = _direct_headers(deepseek_api_key, "deepseek_api_key")
        self._openai_headers = _direct_headers(openai_api_key, "openai_api_key")
        self._timeout_seconds = float(timeout_seconds)

    async def health(self) -> RemoteGpuHealth:
        deepseek_ready, openai_ready = await asyncio.gather(
            self._probe(self._deepseek_url, self._deepseek_headers),
            self._probe(self._openai_url, self._openai_headers),
        )
        capabilities: list[str] = []
        if deepseek_ready:
            capabilities.extend(("chunk_tagging", "retrieval_select", "answer_generate"))
        if openai_ready:
            capabilities.append("embed")
        status: RemoteGpuStatus
        if deepseek_ready and openai_ready:
            status = "ready"
        elif capabilities:
            status = "degraded"
        else:
            status = "unavailable"
        return RemoteGpuHealth(status=status, capabilities=tuple(capabilities))

    async def _probe(self, url: str, headers: Mapping[str, str]) -> bool:
        try:
            response = await self._http_client.get(
                url,
                headers=dict(headers),
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            return True
        except (httpx.HTTPError, TypeError, ValueError):
            return False


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


def _direct_models_url(base_url: str, field_name: str) -> str:
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError(f"{field_name} must be non-blank")
    normalized = base_url.strip().rstrip("/")
    try:
        parsed = httpx.URL(normalized)
        parsed.port
    except (httpx.InvalidURL, ValueError) as error:
        raise ValueError(f"{field_name} must be an HTTPS URL") from error
    if parsed.scheme != "https" or not parsed.host or parsed.query or parsed.fragment:
        raise ValueError(f"{field_name} must be an HTTPS URL")
    return f"{normalized}/models"


def _direct_headers(api_key: str, field_name: str) -> dict[str, str]:
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError(f"{field_name} must be non-blank")
    key = api_key.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in key):
        raise ValueError(f"{field_name} must not contain control characters")
    return {"Authorization": f"Bearer {key}"}
