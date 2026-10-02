"""Typed tracing ports shared by the agent and infrastructure adapters.

The agent depends on this small protocol instead of importing a tracing SDK.
Payloads are copied and redacted at the boundary so a provider adapter cannot
accidentally forward credentials or authorization headers.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import re
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4


class TraceStatus(StrEnum):
    """Lifecycle status for one trace observation."""

    RUNNING = "running"
    OK = "ok"
    ERROR = "error"


class ObservationKind(StrEnum):
    """Kinds supported by the agent tracing topology."""

    TRACE = "trace"
    SPAN = "span"
    TOOL = "tool"
    GENERATION = "generation"


@dataclass(frozen=True, slots=True)
class TraceContext:
    """Stable identifiers used to link parent and child observations."""

    run_id: str
    trace_id: str
    observation_id: str
    parent_observation_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("run_id", "trace_id", "observation_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-blank")
            object.__setattr__(self, field_name, value.strip())
        if self.parent_observation_id is not None:
            if not isinstance(self.parent_observation_id, str) or not self.parent_observation_id.strip():
                raise ValueError("parent_observation_id must be blank or null")
            object.__setattr__(
                self,
                "parent_observation_id",
                self.parent_observation_id.strip(),
            )


@dataclass(frozen=True, slots=True)
class TraceRecord:
    """Immutable snapshot of one completed or in-flight observation."""

    context: TraceContext
    name: str
    kind: ObservationKind
    status: TraceStatus
    input: object | None
    output: object | None
    metadata: Mapping[str, object]
    error_code: str | None
    started_at: datetime
    ended_at: datetime | None
    duration_ms: float | None


class AgentTracer(Protocol):
    """Application port implemented by tracing adapters."""

    @property
    def enabled(self) -> bool:
        """Whether observations are sent to an external tracer."""

    def start_trace(
        self,
        *,
        run_id: str,
        name: str = "agent_run",
        input: object | None = None,
        metadata: Mapping[str, object] | None = None,
        trace_id: str | None = None,
    ) -> "TraceObservation":
        """Start a root trace observation."""

    def start_observation(
        self,
        *,
        run_id: str,
        name: str,
        kind: ObservationKind = ObservationKind.SPAN,
        input: object | None = None,
        metadata: Mapping[str, object] | None = None,
        parent: "TraceObservation | TraceContext | None" = None,
        trace_id: str | None = None,
    ) -> "TraceObservation":
        """Start a child observation linked to ``parent`` when supplied."""

    def flush(self) -> None:
        """Flush buffered observations without exposing provider details."""


class TraceObservation:
    """Context manager representing one observation.

    It supports both ``with`` and ``async with`` so graph nodes and async tool
    adapters can use the same lifecycle contract. Calling ``end`` more than
    once is harmless and preserves the first terminal status.
    """

    def __init__(
        self,
        *,
        context: TraceContext,
        name: str,
        kind: ObservationKind,
        input_payload: object | None,
        metadata: Mapping[str, object] | None,
        close_callback: Callable[["TraceObservation", BaseException | None], None],
        child_factory: Callable[
            ["TraceObservation", str, ObservationKind, object | None, Mapping[str, object] | None],
            "TraceObservation",
        ],
        enabled: bool,
        secrets: Sequence[str] = (),
    ) -> None:
        self.context = context
        self.name = _required_text("name", name)
        self.kind = ObservationKind(kind)
        self._secrets = tuple(secrets)
        self.input = redact_payload(input_payload, secrets=self._secrets)
        self.output: object | None = None
        self.metadata: dict[str, object] = _redacted_mapping(metadata, secrets=self._secrets)
        self.status = TraceStatus.RUNNING
        self.error_code: str | None = None
        self.started_at = datetime.now(timezone.utc)
        self.ended_at: datetime | None = None
        self.duration_ms: float | None = None
        self._started_clock = perf_counter()
        self._close_callback = close_callback
        self._child_factory = child_factory
        self._closed = False
        self.enabled = enabled

    @property
    def observation_id(self) -> str:
        return self.context.observation_id

    @property
    def trace_id(self) -> str:
        return self.context.trace_id

    @property
    def run_id(self) -> str:
        return self.context.run_id

    @property
    def closed(self) -> bool:
        return self._closed

    def set_output(self, value: object | None) -> None:
        if not self._closed:
            self.output = redact_payload(value, secrets=self._secrets)

    def set_metadata(self, values: Mapping[str, object] | None) -> None:
        if self._closed or values is None:
            return
        self.metadata.update(_redacted_mapping(values, secrets=self._secrets))

    def child(
        self,
        name: str,
        *,
        kind: ObservationKind = ObservationKind.SPAN,
        input: object | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> "TraceObservation":
        return self._child_factory(self, name, ObservationKind(kind), input, metadata)

    def span(
        self,
        name: str,
        *,
        input: object | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> "TraceObservation":
        return self.child(name, kind=ObservationKind.SPAN, input=input, metadata=metadata)

    def tool(
        self,
        name: str,
        *,
        input: object | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> "TraceObservation":
        return self.child(name, kind=ObservationKind.TOOL, input=input, metadata=metadata)

    def generation(
        self,
        name: str,
        *,
        input: object | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> "TraceObservation":
        return self.child(
            name,
            kind=ObservationKind.GENERATION,
            input=input,
            metadata=metadata,
        )

    def end(
        self,
        *,
        status: TraceStatus | str = TraceStatus.OK,
        output: object | None = None,
        error: BaseException | None = None,
        error_code: str | None = None,
    ) -> None:
        if self._closed:
            return
        if output is not None:
            self.set_output(output)
        normalized_status = TraceStatus(status)
        if error is not None:
            normalized_status = TraceStatus.ERROR
            error_code = error.__class__.__name__
        if normalized_status is TraceStatus.RUNNING:
            raise ValueError("terminal status must be ok or error")
        if error_code is not None:
            self.error_code = _required_text("error_code", error_code)
        self.status = normalized_status
        self.ended_at = datetime.now(timezone.utc)
        self.duration_ms = max(0.0, (perf_counter() - self._started_clock) * 1000)
        self._closed = True
        self._close_callback(self, error)

    def __enter__(self) -> "TraceObservation":
        return self

    def __exit__(self, exc_type: object, exc_value: BaseException | None, _traceback: object) -> bool:
        self.end(error=exc_value)
        return False

    async def __aenter__(self) -> "TraceObservation":
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: BaseException | None,
        _traceback: object,
    ) -> bool:
        self.end(error=exc_value)
        return False


class NoopTracer:
    """Disabled tracer that preserves lifecycle calls without side effects."""

    enabled = False

    def start_trace(
        self,
        *,
        run_id: str,
        name: str = "agent_run",
        input: object | None = None,
        metadata: Mapping[str, object] | None = None,
        trace_id: str | None = None,
    ) -> TraceObservation:
        return self.start_observation(
            run_id=run_id,
            name=name,
            kind=ObservationKind.TRACE,
            input=input,
            metadata=metadata,
            trace_id=trace_id,
        )

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
        del input, metadata
        parent_context = _parent_context(parent)
        normalized_run_id = _required_text("run_id", run_id)
        context = TraceContext(
            run_id=normalized_run_id,
            trace_id=(parent_context.trace_id if parent_context else trace_id) or uuid4().hex,
            observation_id=uuid4().hex,
            parent_observation_id=(parent_context.observation_id if parent_context else None),
        )
        return TraceObservation(
            context=context,
            name=name,
            kind=kind,
            input_payload=None,
            metadata=None,
            close_callback=lambda _observation, _error: None,
            child_factory=_noop_child,
            enabled=False,
            secrets=(),
        )

    def flush(self) -> None:
        return None


class InMemoryTracer:
    """Deterministic tracer used by contract tests and local diagnostics."""

    enabled = True

    def __init__(self, *, secrets: Sequence[str] = ()) -> None:
        self._secrets = tuple(secret for secret in secrets if isinstance(secret, str) and secret)
        self._observations: dict[str, TraceObservation] = {}
        self._order: list[str] = []

    @property
    def records(self) -> tuple[TraceRecord, ...]:
        return tuple(_record_from_observation(self._observations[identifier]) for identifier in self._order)

    @property
    def traces(self) -> tuple[TraceRecord, ...]:
        """Compatibility alias for callers that call root observations traces."""

        return self.records

    def start_trace(
        self,
        *,
        run_id: str,
        name: str = "agent_run",
        input: object | None = None,
        metadata: Mapping[str, object] | None = None,
        trace_id: str | None = None,
    ) -> TraceObservation:
        return self.start_observation(
            run_id=run_id,
            name=name,
            kind=ObservationKind.TRACE,
            input=input,
            metadata=metadata,
            trace_id=trace_id,
        )

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
        parent_context = _parent_context(parent)
        normalized_run_id = _required_text("run_id", run_id)
        if parent_context is not None and parent_context.run_id != normalized_run_id:
            raise ValueError("parent observation must belong to the same run")
        context = TraceContext(
            run_id=normalized_run_id,
            trace_id=(parent_context.trace_id if parent_context else trace_id) or uuid4().hex,
            observation_id=uuid4().hex,
            parent_observation_id=(parent_context.observation_id if parent_context else None),
        )
        observation = TraceObservation(
            context=context,
            name=name,
            kind=kind,
            input_payload=redact_payload(input, secrets=self._secrets),
            metadata=_redacted_mapping(metadata, secrets=self._secrets),
            close_callback=self._close,
            child_factory=self._child,
            enabled=True,
            secrets=self._secrets,
        )
        self._observations[observation.observation_id] = observation
        self._order.append(observation.observation_id)
        return observation

    def flush(self) -> None:
        return None

    def _child(
        self,
        parent: TraceObservation,
        name: str,
        kind: ObservationKind,
        input: object | None,
        metadata: Mapping[str, object] | None,
    ) -> TraceObservation:
        return self.start_observation(
            run_id=parent.run_id,
            name=name,
            kind=kind,
            input=input,
            metadata=metadata,
            parent=parent,
        )

    def _close(self, observation: TraceObservation, _error: BaseException | None) -> None:
        return None


def redact_payload(value: object | None, *, secrets: Sequence[str] = ()) -> object | None:
    """Return a detached payload with credentials and sensitive headers masked."""

    if value is None:
        return None
    if isinstance(value, Mapping):
        result: dict[object, object] = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                result[key] = "[REDACTED]"
            else:
                result[key] = redact_payload(item, secrets=secrets)
        return result
    if isinstance(value, (list, tuple)):
        converted = [redact_payload(item, secrets=secrets) for item in value]
        return tuple(converted) if isinstance(value, tuple) else converted
    if isinstance(value, (str, int, float, bool)):
        return _redact_text(value, secrets=secrets)
    if isinstance(value, bytes):
        return "[REDACTED_BYTES]"
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return redact_payload(model_dump(), secrets=secrets)
        except Exception:
            return "[UNSERIALIZABLE]"
    return _redact_text(str(value), secrets=secrets)


_SENSITIVE_KEY_RE = re.compile(
    r"(?:api[_-]?key|secret|token|authorization|cookie|password|credential|private[_-]?key)",
    re.IGNORECASE,
)
_ASSIGNMENT_RE = re.compile(
    r"(?P<key>api[_-]?key|secret|token|authorization|cookie|password|credential)"
    r"(?P<separator>\s*[:=]\s*)(?P<value>(?:Bearer\s+)?[^\s,;]+)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


def _redact_text(value: Any, *, secrets: Sequence[str]) -> Any:
    if not isinstance(value, str):
        return value
    redacted = value
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        redacted = redacted.replace(secret, "[REDACTED]")
    redacted = _ASSIGNMENT_RE.sub(_redact_assignment, redacted)
    redacted = _BEARER_RE.sub("Bearer [REDACTED]", redacted)
    return redacted


def _redact_assignment(match: re.Match[str]) -> str:
    value = match.group("value")
    bearer = "Bearer " if value.lower().startswith("bearer ") else ""
    return f"{match.group('key')}{match.group('separator')}{bearer}[REDACTED]"


def _is_sensitive_key(key: object) -> bool:
    return isinstance(key, str) and bool(_SENSITIVE_KEY_RE.search(key))


def _redacted_mapping(
    values: Mapping[str, object] | None,
    *,
    secrets: Sequence[str] = (),
) -> dict[str, object]:
    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise TypeError("metadata must be a mapping")
    redacted = redact_payload(values, secrets=secrets)
    if not isinstance(redacted, dict):
        raise TypeError("metadata must be a mapping")
    return {str(key): value for key, value in redacted.items()}


def _parent_context(parent: TraceObservation | TraceContext | None) -> TraceContext | None:
    if parent is None:
        return None
    if isinstance(parent, TraceContext):
        return parent
    if isinstance(parent, TraceObservation):
        return parent.context
    raise TypeError("parent must be a TraceObservation, TraceContext, or null")


def _required_text(field_name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-blank")
    return value.strip()


def _noop_child(
    parent: TraceObservation,
    name: str,
    kind: ObservationKind,
    input: object | None,
    metadata: Mapping[str, object] | None,
) -> TraceObservation:
    return NoopTracer().start_observation(
        run_id=parent.run_id,
        name=name,
        kind=kind,
        input=input,
        metadata=metadata,
        parent=parent,
    )


def _record_from_observation(observation: TraceObservation) -> TraceRecord:
    return TraceRecord(
        context=observation.context,
        name=observation.name,
        kind=observation.kind,
        status=observation.status,
        input=observation.input,
        output=observation.output,
        metadata=dict(observation.metadata),
        error_code=observation.error_code,
        started_at=observation.started_at,
        ended_at=observation.ended_at,
        duration_ms=observation.duration_ms,
    )


__all__ = [
    "AgentTracer",
    "InMemoryTracer",
    "NoopTracer",
    "ObservationKind",
    "TraceContext",
    "TraceObservation",
    "TraceRecord",
    "TraceStatus",
    "redact_payload",
]
