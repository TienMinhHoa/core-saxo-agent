"""Provider-independent structured observability contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import logging
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from pathlib import Path
from threading import Lock
from typing import Protocol, TextIO


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
    pricing_basis: str | None = None
    document_ref: str | None = None
    stage: str | None = None
    chunk_id: str | None = None
    current_count: int | None = None
    completed_count: int | None = None
    total_count: int | None = None
    progress_percent: float | None = None
    elapsed_seconds: float | None = None
    eta_seconds: float | None = None

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
        if self.pricing_basis is not None and not self.pricing_basis.strip():
            raise ValueError("pricing_basis must be non-blank when provided")
        for field_name in ("document_ref", "stage", "chunk_id"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be non-blank when provided")
        for field_name in ("current_count", "completed_count", "total_count"):
            value = getattr(self, field_name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer")
        if (
            self.completed_count is not None
            and self.total_count is not None
            and self.completed_count > self.total_count
        ):
            raise ValueError("completed_count must not exceed total_count")
        if (
            self.current_count is not None
            and self.total_count is not None
            and self.current_count > self.total_count
        ):
            raise ValueError("current_count must not exceed total_count")
        if self.progress_percent is not None and not 0 <= self.progress_percent <= 100:
            raise ValueError("progress_percent must be between 0 and 100")
        for field_name in ("elapsed_seconds", "eta_seconds"):
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
        log = self._logger.warning if event.result == "warning" else self._logger.info
        log(event.name, extra={"structured_event": event.as_dict()})


class DailyTextFileEventSink(LoggingEventSink):
    """Write safe human-readable events to ``logs/YYYY-MM-DD.log``."""

    def __init__(
        self,
        log_directory: Path,
        *,
        metrics: EventMetrics | None = None,
        clock: Callable[[], datetime] | None = None,
        progress_stream: TextIO | None = None,
    ) -> None:
        if not isinstance(log_directory, Path):
            raise TypeError("log_directory must be a Path")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        self.log_directory = log_directory
        handler = _DailyTextFileHandler(
            log_directory,
            clock=clock or (lambda: datetime.now().astimezone()),
        )
        logger = logging.Logger("saxophone.daily-events", level=logging.INFO)
        logger.propagate = False
        logger.addHandler(handler)
        super().__init__(logger, metrics=metrics)
        self._progress_stream = progress_stream

    def emit(self, event: StructuredEvent) -> None:
        super().emit(event)
        if event.name == "ingestion.progress" and self._progress_stream is not None:
            self._progress_stream.write(_format_console_progress(event.as_dict()))
            self._progress_stream.write("\n")
            self._progress_stream.flush()


class _DailyTextFileHandler(logging.Handler):
    def __init__(
        self,
        log_directory: Path,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        super().__init__(level=logging.INFO)
        self._log_directory = log_directory
        self._clock = clock

    def emit(self, record: logging.LogRecord) -> None:
        try:
            event = getattr(record, "structured_event", None)
            if not isinstance(event, Mapping):
                return
            now = self._clock()
            self._log_directory.mkdir(parents=True, exist_ok=True)
            target = self._log_directory / f"{now.date().isoformat()}.log"
            with target.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(_format_text_event(now, record.levelname, event))
                stream.write("\n")
        except Exception:
            self.handleError(record)


def _format_text_event(
    timestamp: datetime,
    level: str,
    event: Mapping[str, object],
) -> str:
    input_tokens = event.get("input_tokens")
    output_tokens = event.get("output_tokens")
    total_tokens = (
        input_tokens + output_tokens
        if isinstance(input_tokens, int) and isinstance(output_tokens, int)
        else "n/a"
    )
    cost = event.get("cost_usd")
    estimated_cost = f"{cost:.12f}" if isinstance(cost, (int, float)) else "n/a"
    fields = (
        ("timestamp", timestamp.isoformat()),
        ("level", level),
        ("event", event.get("name", "unknown")),
        ("correlation_id", event.get("correlation_id", "unknown")),
        ("task", event.get("task", "unknown")),
        ("model", event.get("model", "unknown")),
        ("attempt", event.get("attempt", "unknown")),
        ("duration_ms", event.get("duration_ms", "unknown")),
        ("input_tokens", input_tokens if input_tokens is not None else "n/a"),
        ("output_tokens", output_tokens if output_tokens is not None else "n/a"),
        ("total_tokens", total_tokens),
        ("estimated_cost_usd", estimated_cost),
        ("pricing_basis", event.get("pricing_basis", "n/a")),
        ("result", event.get("result", "unknown")),
        ("reason_code", event.get("reason_code", "n/a")),
        ("document_ref", event.get("document_ref", "n/a")),
        ("stage", event.get("stage", "n/a")),
        ("chunk_id", event.get("chunk_id", "n/a")),
        ("current", event.get("current_count", "n/a")),
        ("completed", event.get("completed_count", "n/a")),
        ("total", event.get("total_count", "n/a")),
        ("progress_percent", _format_decimal(event.get("progress_percent"), 2)),
        ("elapsed_seconds", _format_decimal(event.get("elapsed_seconds"), 1)),
        ("eta_seconds", _format_decimal(event.get("eta_seconds"), 1)),
    )
    return " | ".join(f"{name}={value}" for name, value in fields)


def _format_console_progress(event: Mapping[str, object]) -> str:
    completed = event.get("completed_count", 0)
    total = event.get("total_count", 0)
    current = event.get("current_count")
    count = f"completed={completed}/{total}"
    if isinstance(current, int):
        count = f"chunk={current}/{total} {count}"
    percentage = _format_decimal(event.get("progress_percent"), 2)
    elapsed = _format_decimal(event.get("elapsed_seconds"), 1)
    eta = _format_decimal(event.get("eta_seconds"), 1)
    chunk = event.get("chunk_id")
    chunk_field = f" chunk_id={chunk}" if isinstance(chunk, str) else ""
    return (
        f"[INGEST] stage={event.get('stage', 'unknown')} "
        f"status={event.get('result', 'unknown')} {count} "
        f"progress={percentage}% elapsed={elapsed}s eta={eta}s{chunk_field}"
    )


def _format_decimal(value: object, digits: int) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.{digits}f}"
    return "n/a"
