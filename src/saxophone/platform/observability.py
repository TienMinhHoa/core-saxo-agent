"""Provider-independent structured observability contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import logging
from collections import Counter, defaultdict
from threading import Lock
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StructuredEvent:
    """Safe event envelope; it deliberately contains no request payloads."""

    name: str
    correlation_id: str
    task: str
    model: str
    attempt: int
    duration_ms: float
    input_count: int
    output_count: int
    result: str
    reason_code: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None

    def __post_init__(self) -> None:
        for field_name in ("name", "correlation_id", "task", "model", "result"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-blank")
        if self.attempt < 1:
            raise ValueError("attempt must be positive")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must not be negative")
        if self.input_count < 0:
            raise ValueError("input_count must not be negative")
        if self.output_count < 0:
            raise ValueError("output_count must not be negative")
        if self.reason_code is not None and not self.reason_code.strip():
            raise ValueError("reason_code must be non-blank when provided")
        for field_name in ("input_tokens", "output_tokens", "cost_usd"):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must not be negative")

    def as_dict(self) -> dict[str, object]:
        """Return the allowlisted event fields for a structured logger."""

        return {key: value for key, value in asdict(self).items() if value is not None}


class EventSink(Protocol):
    """Application port for emitting safe structured events."""

    def emit(self, event: StructuredEvent) -> None:
        """Publish one event without receiving sensitive payload data."""


class InMemoryEventSink:
    """Small deterministic sink for contract and integration tests."""

    def __init__(self) -> None:
        self.events: list[StructuredEvent] = []

    def emit(self, event: StructuredEvent) -> None:
        self.events.append(event)


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    """Immutable point-in-time view for diagnostics and operational consumers."""

    counts: tuple[tuple[str, str, str, int], ...]
    durations_ms: tuple[tuple[str, tuple[float, ...]], ...]
    in_flight: tuple[tuple[str, int], ...]
    max_concurrency: tuple[tuple[str, int], ...]
    token_usage: tuple[tuple[str, int, int], ...] = ()
    cost_usd: tuple[tuple[str, float], ...] = ()


class EventMetrics:
    """Deterministic in-process counters for the minimum observability metrics."""

    def __init__(self) -> None:
        self._counts: Counter[tuple[str, str, str]] = Counter()
        self._durations_ms: defaultdict[str, list[float]] = defaultdict(list)
        self._in_flight: Counter[str] = Counter()
        self._max_concurrency: Counter[str] = Counter()
        self._token_usage: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
        self._cost_usd: defaultdict[str, float] = defaultdict(float)
        self._lock = Lock()

    def observe(self, event: StructuredEvent) -> None:
        with self._lock:
            self._counts[(event.name, event.task, event.result)] += 1
            self._durations_ms[event.task].append(event.duration_ms)
            if event.input_tokens is not None:
                self._token_usage[event.task][0] += event.input_tokens
            if event.output_tokens is not None:
                self._token_usage[event.task][1] += event.output_tokens
            if event.cost_usd is not None:
                self._cost_usd[event.task] += event.cost_usd

    def request_started(self, *, task: str) -> None:
        with self._lock:
            self._in_flight[task] += 1
            self._max_concurrency[task] = max(
                self._max_concurrency[task], self._in_flight[task]
            )

    def request_finished(self, *, task: str) -> None:
        with self._lock:
            if self._in_flight[task] <= 0:
                raise ValueError("request_finished called without a matching start")
            self._in_flight[task] -= 1

    def count(self, *, name: str, task: str, result: str) -> int:
        with self._lock:
            return self._counts[(name, task, result)]

    def durations_ms(self, *, task: str) -> tuple[float, ...]:
        with self._lock:
            return tuple(self._durations_ms[task])

    def in_flight(self, *, task: str) -> int:
        with self._lock:
            return self._in_flight[task]

    def max_concurrency(self, *, task: str) -> int:
        with self._lock:
            return self._max_concurrency[task]

    def token_usage(self, *, task: str) -> tuple[int, int]:
        with self._lock:
            values = self._token_usage[task]
            return values[0], values[1]

    def cost_usd(self, *, task: str) -> float:
        with self._lock:
            return self._cost_usd[task]

    def snapshot(self) -> MetricsSnapshot:
        """Return one consistent, detached view of all collected metrics."""

        with self._lock:
            return MetricsSnapshot(
                counts=tuple(
                    (*key, value) for key, value in sorted(self._counts.items())
                ),
                durations_ms=tuple(
                    (task, tuple(values))
                    for task, values in sorted(self._durations_ms.items())
                ),
                in_flight=tuple(sorted(self._in_flight.items())),
                max_concurrency=tuple(sorted(self._max_concurrency.items())),
                token_usage=tuple(
                    (task, values[0], values[1])
                    for task, values in sorted(self._token_usage.items())
                ),
                cost_usd=tuple(sorted(self._cost_usd.items())),
            )


class LoggingEventSink:
    """Publish safe structured events through the standard logging boundary."""

    def __init__(
        self,
        logger: logging.Logger | None = None,
        *,
        metrics: EventMetrics | None = None,
    ) -> None:
        self._logger = logger or logging.getLogger("saxophone.events")
        self.metrics = metrics

    def emit(self, event: StructuredEvent) -> None:
        if self.metrics is not None:
            self.metrics.observe(event)
        self._logger.info(event.name, extra={"structured_event": event.as_dict()})
