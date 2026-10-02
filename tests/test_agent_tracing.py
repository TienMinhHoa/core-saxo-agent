from __future__ import annotations

import pytest

from saxophone.agent.tracing import (
    InMemoryTracer,
    NoopTracer,
    ObservationKind,
    TraceStatus,
    redact_payload,
)
from saxophone.app.factory import AppOverrides, create_app
from saxophone.app.settings import AppSettings, SettingsValidationError
from saxophone.platform.langfuse_tracing import LangfuseTracer, create_langfuse_tracer


VALID_ENVIRONMENT = {
    "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
    "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token-must-not-leak",
}


def test_redact_payload_masks_nested_credentials_and_bearer_headers() -> None:
    payload = redact_payload(
        {
            "authorization": "Bearer header-secret",
            "nested": {"api_key": "key-secret", "message": "token=inline-secret"},
            "text": "Authorization: Bearer another-secret",
        },
        secrets=("header-secret", "key-secret"),
    )

    assert payload == {
        "authorization": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]", "message": "token=[REDACTED]"},
        "text": "Authorization: Bearer [REDACTED]",
    }


def test_in_memory_tracer_keeps_parent_child_topology_and_redacts_outputs() -> None:
    tracer = InMemoryTracer(secrets=("private-value",))

    with tracer.start_trace(
        run_id="run-1",
        input={"question": "safe", "authorization": "private-value"},
    ) as trace:
        with trace.tool("document_search", input={"query": "safe"}) as tool:
            tool.set_output({"answer": "safe", "api_key": "private-value"})

    records = tracer.records
    assert [record.kind for record in records] == [ObservationKind.TRACE, ObservationKind.TOOL]
    assert records[1].context.trace_id == records[0].context.trace_id
    assert records[1].context.parent_observation_id == records[0].context.observation_id
    assert records[0].input == {"question": "safe", "authorization": "[REDACTED]"}
    assert records[1].output == {"answer": "safe", "api_key": "[REDACTED]"}
    assert records[0].status is TraceStatus.OK
    assert records[1].duration_ms is not None


def test_observation_closes_with_error_details_when_context_raises() -> None:
    tracer = InMemoryTracer()

    with pytest.raises(RuntimeError, match="boom"):
        with tracer.start_trace(run_id="run-error"):
            raise RuntimeError("boom")

    record = tracer.records[0]
    assert record.status is TraceStatus.ERROR
    assert record.error_code == "RuntimeError"
    assert record.ended_at is not None


@pytest.mark.anyio
async def test_noop_tracer_supports_async_lifecycle_without_side_effects() -> None:
    tracer = NoopTracer()
    async with tracer.start_trace(run_id="run-noop") as trace:
        child = trace.span("validation")
        child.set_output({"authorization": "secret"})
        child.end()

    assert tracer.enabled is False
    assert trace.closed is True
    assert child.closed is True


class _FakeRemoteObservation:
    def __init__(self, calls: list[tuple[str, dict[str, object]]]) -> None:
        self._calls = calls

    def span(self, **kwargs: object) -> "_FakeRemoteObservation":
        self._calls.append(("span", kwargs))
        return _FakeRemoteObservation(self._calls)

    def generation(self, **kwargs: object) -> "_FakeRemoteObservation":
        self._calls.append(("generation", kwargs))
        return _FakeRemoteObservation(self._calls)

    def end(self, **kwargs: object) -> None:
        self._calls.append(("end", kwargs))


class _FakeLangfuse:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def trace(self, **kwargs: object) -> _FakeRemoteObservation:
        self.calls.append(("trace", kwargs))
        return _FakeRemoteObservation(self.calls)

    def flush(self) -> None:
        self.calls.append(("flush", {}))


def test_langfuse_adapter_preserves_topology_and_redacts_remote_payloads() -> None:
    client = _FakeLangfuse()
    tracer = LangfuseTracer(
        secret_key="secret-key",
        public_key="public-key",
        base_url="https://langfuse.example.test",
        client=client,
    )

    with tracer.start_trace(run_id="run-remote", input={"api_key": "secret-key"}) as trace:
        with trace.generation("answer") as generation:
            generation.set_output({"authorization": "Bearer secret-key", "answer": "ok"})

    assert tracer.enabled is True
    assert client.calls[0][0] == "trace"
    assert client.calls[0][1]["input"] == {"api_key": "[REDACTED]"}
    assert [call[0] for call in client.calls[1:]] == ["generation", "end", "end"]
    assert "secret-key" not in repr(client.calls)

    tracer.flush()
    assert client.calls[-1][0] == "flush"


def test_create_langfuse_tracer_defaults_to_noop_without_complete_configuration() -> None:
    settings = AppSettings.from_environment(VALID_ENVIRONMENT)

    tracer = create_langfuse_tracer(settings)

    assert isinstance(tracer, NoopTracer)
    assert tracer.enabled is False


def test_factory_exposes_one_shared_tracer_and_accepts_test_override() -> None:
    settings = AppSettings.from_environment(VALID_ENVIRONMENT)
    tracer = InMemoryTracer()

    app = create_app(settings, overrides=AppOverrides(tracer=tracer))

    assert app.state.container.tracer is tracer


def test_settings_parse_langfuse_credentials_without_leaking_secret() -> None:
    settings = AppSettings.from_environment(
        {
            **VALID_ENVIRONMENT,
            "SAXO_LANGFUSE_ENABLED": "true",
            "LANGFUSE_SECRET_KEY": "secret-key",
            "LANGFUSE_PUBLIC_KEY": "public-key",
            "LANGFUSE_BASE_URL": "https://langfuse.example.test",
        }
    )

    assert settings.langfuse_enabled is True
    assert settings.langfuse_public_key == "public-key"
    assert settings.langfuse_base_url == "https://langfuse.example.test"
    assert "secret-key" not in repr(settings)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://langfuse.example.test",
        "http://100.110.177.94:3000",
        "https://langfuse.example.test",
    ],
)
def test_settings_accepts_http_or_https_langfuse_url(base_url: str) -> None:
    settings = AppSettings.from_environment(
        {
            **VALID_ENVIRONMENT,
            "LANGFUSE_BASE_URL": base_url,
        }
    )

    assert settings.langfuse_base_url == base_url


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("LANGFUSE_BASE_URL", "ftp://langfuse.example.test"),
        ("LANGFUSE_BASE_URL", "langfuse.example.test"),
        ("LANGFUSE_BASE_URL", "https://key@langfuse.example.test"),
        ("LANGFUSE_BASE_URL", "https://langfuse.example.test?debug=true"),
        ("LANGFUSE_BASE_URL", "https://langfuse.example.test#fragment"),
    ],
)
def test_settings_reject_unsafe_langfuse_url(variable: str, value: str) -> None:
    with pytest.raises(SettingsValidationError, match=variable):
        AppSettings.from_environment({**VALID_ENVIRONMENT, variable: value})


def test_settings_require_all_langfuse_credentials_when_enabled() -> None:
    with pytest.raises(SettingsValidationError, match="LANGFUSE_SECRET_KEY"):
        AppSettings.from_environment(
            {
                **VALID_ENVIRONMENT,
                "SAXO_LANGFUSE_ENABLED": "true",
                "LANGFUSE_PUBLIC_KEY": "public-key",
                "LANGFUSE_BASE_URL": "https://langfuse.example.test",
            }
        )
