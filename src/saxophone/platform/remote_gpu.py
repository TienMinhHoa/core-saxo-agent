"""Contracts for the remote GPU boundary.

The first Phase 1 slice deliberately provides only a lifecycle-safe local
fallback.  The HTTP submit/poll adapter belongs behind this contract in a
later slice, so importing or composing the app cannot start GPU work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


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
