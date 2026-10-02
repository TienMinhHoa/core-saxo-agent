from __future__ import annotations

from saxophone.app.factory import AppOverrides, _compose_model_clients
from saxophone.app.settings import AppSettings
from saxophone.platform.observability import InMemoryEventSink


class _Gateway:
    async def health(self):
        raise AssertionError("composition test must not call health")


class _ModelClient:
    async def invoke(self, request):
        raise AssertionError("composition test must not invoke the model")


def test_model_composition_preserves_injected_clients_and_providers() -> None:
    settings = AppSettings.from_environment(
        {
            "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
            "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
        }
    )
    gateway = _Gateway()
    model_client = _ModelClient()
    event_sink = InMemoryEventSink()
    structured_provider = object()
    agent_structured_provider = object()

    composition = _compose_model_clients(
        settings,
        AppOverrides(
            remote_gpu_gateway=gateway,
            model_client=model_client,
            event_sink=event_sink,
            structured_llm_provider=structured_provider,
            agent_structured_llm_provider=agent_structured_provider,
        ),
    )

    assert composition.remote_gpu_gateway is gateway
    assert composition.model_client is model_client
    assert composition.event_sink is event_sink
    assert composition.metrics is None
    assert composition.http_client is None
    assert composition.structured_llm_provider is structured_provider
    assert composition.agent_structured_llm_provider is agent_structured_provider

