"""Optional Langfuse adapter for the agent tracing port.

The SDK is intentionally imported lazily. A local installation without
Langfuse credentials therefore keeps the same application behavior through a
no-op tracer, while tests can inject a small fake client without network I/O.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from saxophone.agent.tracing import (
    AgentTracer,
    InMemoryTracer,
    NoopTracer,
    ObservationKind,
    TraceContext,
    TraceObservation,
    redact_payload,
)


class LangfuseTracer(InMemoryTracer):
    """Bridge the typed agent tracer to a Langfuse-compatible client.

    ``InMemoryTracer`` supplies stable IDs and redacted records locally. The
    optional client receives the same lifecycle calls when available; any
    client failure is swallowed so tracing never changes agent behavior.
    """

    def __init__(
        self,
        *,
        secret_key: str | None,
        public_key: str | None,
        base_url: str | None,
        enabled: bool = True,
        client: object | None = None,
    ) -> None:
        self._client = client
        self._external_enabled = bool(enabled and secret_key and public_key and base_url)
        secrets = tuple(value for value in (secret_key, public_key) if value)
        super().__init__(secrets=secrets)
        if self._external_enabled and self._client is None:
            self._client = _build_client(
                secret_key=secret_key or "",
                public_key=public_key or "",
                base_url=base_url or "",
            )
        self._external_enabled = self._external_enabled and self._client is not None

    @property
    def enabled(self) -> bool:
        return self._external_enabled

    def start_trace(
        self,
        *,
        run_id: str,
        name: str = "agent_run",
        input: object | None = None,
        metadata: Mapping[str, object] | None = None,
        trace_id: str | None = None,
    ) -> TraceObservation:
        local = super().start_trace(
            run_id=run_id,
            name=name,
            input=input,
            metadata=metadata,
            trace_id=trace_id,
        )
        remote = self._start_remote_trace(local)
        return _LangfuseObservation(local, remote, self)

    def start_observation(
        self,
        *,
        run_id: str,
        name: str,
        kind: ObservationKind = ObservationKind.SPAN,
        input: object | None = None,
        metadata: Mapping[str, object] | None = None,
        parent: TraceObservation | TraceContext | None = None,
        trace_id: str | None = None,
    ) -> TraceObservation:
        local_parent = parent._local if isinstance(parent, _LangfuseObservation) else parent
        local = super().start_observation(
            run_id=run_id,
            name=name,
            kind=kind,
            input=input,
            metadata=metadata,
            parent=local_parent,
            trace_id=trace_id,
        )
        remote_parent = parent._remote if isinstance(parent, _LangfuseObservation) else None
        remote = self._start_remote_observation(
            local,
            remote_parent=remote_parent,
        )
        return _LangfuseObservation(local, remote, self)

    def flush(self) -> None:
        if not self._external_enabled or self._client is None:
            return None
        flush = getattr(self._client, "flush", None)
        if callable(flush):
            try:
                flush()
            except Exception:
                return None

    def _start_remote_trace(self, local: TraceObservation) -> object | None:
        if not self._external_enabled or self._client is None:
            return None
        trace = getattr(self._client, "trace", None)
        if not callable(trace):
            return None
        try:
            return trace(
                id=local.trace_id,
                name=local.name,
                input=local.input,
                metadata=dict(local.metadata),
                session_id=local.run_id,
            )
        except Exception:
            return None

    def _start_remote_observation(
        self,
        local: TraceObservation,
        *,
        remote_parent: object | None,
    ) -> object | None:
        if not self._external_enabled or self._client is None:
            return None
        parent_method = _observation_method(remote_parent, local.kind)
        if parent_method is not None:
            try:
                return parent_method(
                    name=local.name,
                    input=local.input,
                    metadata=dict(local.metadata),
                )
            except Exception:
                return None
        generic = getattr(self._client, "span", None)
        if not callable(generic):
            return None
        try:
            return generic(
                trace_id=local.trace_id,
                id=local.observation_id,
                name=local.name,
                input=local.input,
                metadata=dict(local.metadata),
                parent_observation_id=local.context.parent_observation_id,
            )
        except Exception:
            return None

    def _finish_remote(self, observation: TraceObservation, remote: object | None) -> None:
        if remote is None:
            return
        payload = {
            "output": redact_payload(observation.output),
            "metadata": dict(observation.metadata),
            "status_message": observation.error_code,
        }
        end = getattr(remote, "end", None)
        if callable(end):
            try:
                end(**payload)
                return
            except TypeError:
                try:
                    end(output=payload["output"])
                    return
                except Exception:
                    return
            except Exception:
                return
        update = getattr(remote, "update", None)
        if callable(update):
            try:
                update(**payload)
            except Exception:
                return


class _LangfuseObservation(TraceObservation):
    def __init__(
        self,
        local: TraceObservation,
        remote: object | None,
        tracer: LangfuseTracer,
    ) -> None:
        self._local = local
        self._remote = remote
        self._tracer = tracer

    @property
    def context(self) -> TraceContext:
        return self._local.context

    @property
    def name(self) -> str:
        return self._local.name

    @property
    def kind(self) -> ObservationKind:
        return self._local.kind

    @property
    def input(self) -> object | None:
        return self._local.input

    @property
    def output(self) -> object | None:
        return self._local.output

    @property
    def metadata(self) -> dict[str, object]:
        return self._local.metadata

    @property
    def status(self):
        return self._local.status

    @property
    def error_code(self) -> str | None:
        return self._local.error_code

    @property
    def started_at(self):
        return self._local.started_at

    @property
    def ended_at(self):
        return self._local.ended_at

    @property
    def duration_ms(self):
        return self._local.duration_ms

    @property
    def enabled(self) -> bool:
        return self._tracer.enabled

    @property
    def closed(self) -> bool:
        return self._local.closed

    @property
    def observation_id(self) -> str:
        return self._local.observation_id

    @property
    def trace_id(self) -> str:
        return self._local.trace_id

    @property
    def run_id(self) -> str:
        return self._local.run_id

    def set_output(self, value: object | None) -> None:
        self._local.set_output(value)

    def set_metadata(self, values: Mapping[str, object] | None) -> None:
        self._local.set_metadata(values)

    def child(
        self,
        name: str,
        *,
        kind: ObservationKind = ObservationKind.SPAN,
        input: object | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> TraceObservation:
        return self._tracer.start_observation(
            run_id=self.run_id,
            name=name,
            kind=kind,
            input=input,
            metadata=metadata,
            parent=self,
        )

    def end(self, **kwargs: Any) -> None:
        if self._local.closed:
            return
        self._local.end(**kwargs)
        self._tracer._finish_remote(self._local, self._remote)

    def __enter__(self) -> "_LangfuseObservation":
        return self

    def __exit__(self, exc_type: object, exc_value: BaseException | None, traceback: object) -> bool:
        self.end(error=exc_value)
        return False

    async def __aenter__(self) -> "_LangfuseObservation":
        return self

    async def __aexit__(self, exc_type: object, exc_value: BaseException | None, traceback: object) -> bool:
        self.end(error=exc_value)
        return False


def create_langfuse_tracer(settings: object, *, client: object | None = None) -> AgentTracer:
    """Create a configured adapter, falling back to a disabled tracer safely."""

    enabled = bool(getattr(settings, "langfuse_enabled", False))
    secret_key = getattr(settings, "langfuse_secret_key", None)
    public_key = getattr(settings, "langfuse_public_key", None)
    base_url = getattr(settings, "langfuse_base_url", None)
    if not enabled or not all(isinstance(value, str) and value.strip() for value in (secret_key, public_key, base_url)):
        return NoopTracer()
    tracer = LangfuseTracer(
        secret_key=secret_key,
        public_key=public_key,
        base_url=base_url,
        enabled=enabled,
        client=client,
    )
    return tracer if tracer.enabled else NoopTracer()


def _observation_method(remote: object | None, kind: ObservationKind):
    if remote is None:
        return None
    if kind is ObservationKind.GENERATION:
        return getattr(remote, "generation", None) or getattr(remote, "span", None)
    if kind is ObservationKind.TOOL:
        return getattr(remote, "span", None) or getattr(remote, "observation", None)
    return getattr(remote, "span", None) or getattr(remote, "observation", None)


def _build_client(*, secret_key: str, public_key: str, base_url: str) -> object | None:
    try:
        from langfuse import Langfuse
    except ImportError:
        return None
    try:
        return Langfuse(secret_key=secret_key, public_key=public_key, host=base_url)
    except TypeError:
        try:
            return Langfuse(secret_key=secret_key, public_key=public_key, base_url=base_url)
        except Exception:
            return None
    except Exception:
        return None


__all__ = ["LangfuseTracer", "create_langfuse_tracer"]
