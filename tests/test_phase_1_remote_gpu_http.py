from __future__ import annotations

import asyncio

import httpx

from saxophone.app.settings import AppSettings
from saxophone.platform.remote_gpu import CachedRemoteGpuGateway, HttpRemoteGpuGateway, RemoteGpuHealth


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
            gateway = HttpRemoteGpuGateway(
                build_settings(), http_client=client, timeout_seconds=5.0
            )

            health = await gateway.health()

            assert health.status == "ready"
            assert health.capabilities == ("embed", "pdf_extract")

    asyncio.run(verify())
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert str(requests[0].url) == "https://gpu.example.test/api/v1/health"
    assert requests[0].headers["Authorization"] == "Bearer token-used-only-in-contract-test"


def test_health_uses_configured_timeout() -> None:
    timeouts: list[object] = []

    async def verify() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            timeouts.append(request.extensions.get("timeout"))
            return httpx.Response(200, json={"status": "ready"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = HttpRemoteGpuGateway(
                build_settings(),
                http_client=client,
                timeout_seconds=2.5,
            )

            await gateway.health()

    asyncio.run(verify())
    assert timeouts == [{"connect": 2.5, "read": 2.5, "write": 2.5, "pool": 2.5}]


def test_health_preserves_only_the_supported_remote_statuses() -> None:
    async def verify(status: str) -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": status})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = HttpRemoteGpuGateway(
                build_settings(), http_client=client, timeout_seconds=5.0
            )

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
            gateway = HttpRemoteGpuGateway(
                build_settings(), http_client=client, timeout_seconds=5.0
            )

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
            gateway = HttpRemoteGpuGateway(
                build_settings(), http_client=client, timeout_seconds=5.0
            )

            health = await gateway.health()

        assert health.status == "unavailable"

    asyncio.run(verify())


def test_health_returns_safe_unavailable_status_for_wrong_transport_response_type() -> None:
    async def verify() -> None:
        class BrokenHttpClient:
            async def get(self, *_args: object, **_kwargs: object) -> object:
                return object()

        gateway = HttpRemoteGpuGateway(
            build_settings(), http_client=BrokenHttpClient(), timeout_seconds=5.0  # type: ignore[arg-type]
        )

        health = await gateway.health()

        assert health == RemoteGpuHealth(status="unavailable")

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
            gateway = HttpRemoteGpuGateway(
                build_settings(), http_client=client, timeout_seconds=5.0
            )

            health = await gateway.health()

        assert health.status == "ready"
        assert health.capabilities == ("embed", "pdf_extract")

    asyncio.run(verify())


def test_cached_health_reuses_result_until_ttl_expires() -> None:
    async def verify() -> None:
        class FakeGateway:
            calls = 0

            async def health(self) -> RemoteGpuHealth:
                self.calls += 1
                return RemoteGpuHealth(status="ready", capabilities=("embed",))

        now = [100.0]
        gateway = FakeGateway()
        cached = CachedRemoteGpuGateway(gateway, ttl_seconds=5.0, clock=lambda: now[0])

        first = await cached.health()
        second = await cached.health()
        now[0] = 105.0
        third = await cached.health()

        assert first == second == third
        assert gateway.calls == 2

    asyncio.run(verify())
