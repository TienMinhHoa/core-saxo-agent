"""Provider-independent structured observability contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import logging
from collections import Counter, defaultdict
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


class EventMetrics:
    """Deterministic in-process counters for the minimum observability metrics."""

    def __init__(self) -> None:
        self._counts: Counter[tuple[str, str, str]] = Counter()
        self._durations_ms: defaultdict[str, list[float]] = defaultdict(list)

    def observe(self, event: StructuredEvent) -> None:
        self._counts[(event.name, event.task, event.result)] += 1
        self._durations_ms[event.task].append(event.duration_ms)

    def count(self, *, name: str, task: str, result: str) -> int:
        return self._counts[(name, task, result)]

    def durations_ms(self, *, task: str) -> tuple[float, ...]:
        return tuple(self._durations_ms[task])


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
