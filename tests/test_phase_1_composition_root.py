from __future__ import annotations

import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from saxophone.app.factory import AppContainer, AppOverrides, create_app
from saxophone.app.settings import AppSettings
from saxophone.platform.remote_gpu import RemoteGpuHealth


VALID_ENVIRONMENT = {
    "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
    "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token-must-not-leak",
}


class FakeRemoteGpuGateway:
    def __init__(self, status: str) -> None:
        self.status = status
        self.health_requests = 0

    async def health(self) -> RemoteGpuHealth:
        self.health_requests += 1
        return RemoteGpuHealth(status=self.status)


def build_settings() -> AppSettings:
    return AppSettings.from_environment(VALID_ENVIRONMENT)


def test_runtime_modules_import_without_reading_environment_or_starting_provider(
    monkeypatch,
) -> None:
    def reject_environment_access(*_args, **_kwargs):
        raise AssertionError("runtime module must not read process environment at import time")

    monkeypatch.setattr("os.getenv", reject_environment_access)
    monkeypatch.setattr("os.environ.get", reject_environment_access)

    assert importlib.import_module("saxophone.main")
    assert importlib.import_module("saxophone.app.factory")


def test_create_app_composes_fastapi_and_exposes_container() -> None:
    gateway = FakeRemoteGpuGateway(status="ready")

    app = create_app(build_settings(), overrides=AppOverrides(remote_gpu_gateway=gateway))

    assert isinstance(app, FastAPI)
    assert isinstance(app.state.container, AppContainer)
    assert app.state.container.settings == build_settings()
    assert app.state.container.remote_gpu_gateway is gateway


def test_health_uses_override_and_returns_stable_disabled_capabilities() -> None:
    gateway = FakeRemoteGpuGateway(status="degraded")
    app = create_app(build_settings(), overrides=AppOverrides(remote_gpu_gateway=gateway))

    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "app": "ready",
        "remote_gpu": "degraded",
        "extraction": "disabled",
        "ingestion": "disabled",
        "retrieval": "disabled",
        "chat": "disabled",
    }
    assert gateway.health_requests == 1


def test_health_preserves_unavailable_remote_gpu_status() -> None:
    gateway = FakeRemoteGpuGateway(status="unavailable")
    app = create_app(build_settings(), overrides=AppOverrides(remote_gpu_gateway=gateway))

    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["remote_gpu"] == "unavailable"


def test_health_does_not_disclose_connection_secrets_or_local_paths() -> None:
    gateway = FakeRemoteGpuGateway(status="ready")
    app = create_app(build_settings(), overrides=AppOverrides(remote_gpu_gateway=gateway))

    response = TestClient(app).get("/api/v1/health")

    body = response.text
    assert VALID_ENVIRONMENT["SAXO_REMOTE_GPU_BEARER_TOKEN"] not in body
    assert build_settings().remote_gpu_base_url not in body
    assert str(build_settings().data_root) not in body
