from __future__ import annotations

import asyncio

import httpx

from saxophone.app.settings import AppSettings
from saxophone.platform.remote_gpu import HttpRemoteGpuGateway


ENVIRONMENT = {
    "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test/api/",
    "SAXO_REMOTE_GPU_BEARER_TOKEN": "token-used-only-in-contract-test",
}


def build_settings() -> AppSettings:
    return AppSettings.from_environment(ENVIRONMENT)


def test_health_uses_shared_client_with_https_bearer_auth_and_stable_path() -> None:
    requests: list[httpx.Request] = []

    async def verify() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"status": "ready", "capabilities": ["embed", "pdf_extract"]},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = HttpRemoteGpuGateway(build_settings(), http_client=client)

            health = await gateway.health()

        assert health.status == "ready"
        assert health.capabilities == ("embed", "pdf_extract")

    asyncio.run(verify())
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert str(requests[0].url) == "https://gpu.example.test/api/v1/health"
    assert requests[0].headers["Authorization"] == "Bearer token-used-only-in-contract-test"


def test_health_preserves_only_the_supported_remote_statuses() -> None:
    async def verify(status: str) -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": status})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = HttpRemoteGpuGateway(build_settings(), http_client=client)

            health = await gateway.health()

        assert health.status == status
        assert health.capabilities == ()

    for status in ("ready", "degraded", "unavailable"):
        asyncio.run(verify(status))


def test_health_returns_safe_unavailable_status_for_http_or_contract_failure() -> None:
    async def verify(response: httpx.Response) -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return response

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = HttpRemoteGpuGateway(build_settings(), http_client=client)

            health = await gateway.health()

        assert health.status == "unavailable"
        assert health.capabilities == ()

    for response in (
        httpx.Response(401, json={"detail": "unauthorized"}),
        httpx.Response(503, json={"detail": "temporarily unavailable"}),
        httpx.Response(200, json={"status": "unknown"}),
        httpx.Response(200, json={}),
    ):
        asyncio.run(verify(response))


def test_health_returns_safe_unavailable_status_when_transport_fails() -> None:
    async def verify() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("GPU did not answer", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = HttpRemoteGpuGateway(build_settings(), http_client=client)

            health = await gateway.health()

        assert health.status == "unavailable"

    asyncio.run(verify())


def test_health_filters_malformed_and_duplicate_capabilities_without_leaking_payloads() -> None:
    async def verify() -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "ready",
                    "capabilities": ["embed", "", "embed", 42, "  pdf_extract  "],
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = HttpRemoteGpuGateway(build_settings(), http_client=client)

            health = await gateway.health()

        assert health.status == "ready"
        assert health.capabilities == ("embed", "pdf_extract")

    asyncio.run(verify())
