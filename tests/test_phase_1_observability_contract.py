from __future__ import annotations

import pytest
import logging

from saxophone.platform.observability import (
    EventMetrics,
    InMemoryEventSink,
    LoggingEventSink,
    StructuredEvent,
)


def test_event_metrics_counts_results_and_preserves_task_durations() -> None:
    metrics = EventMetrics()
    sink = LoggingEventSink(metrics=metrics)
    event = StructuredEvent(
        name="model.request.completed",
        correlation_id="corr-metrics",
        task="embed",
        model="profile-v1",
        attempt=1,
        duration_ms=4.5,
        input_count=2,
        output_count=1,
        result="success",
    )

    sink.emit(event)

    assert metrics.count(
        name="model.request.completed", task="embed", result="success"
    ) == 1
    assert metrics.durations_ms(task="embed") == (4.5,)


def test_event_metrics_tracks_in_flight_and_peak_concurrency_per_task() -> None:
    metrics = EventMetrics()

    metrics.request_started(task="embed")
    metrics.request_started(task="embed")
    metrics.request_finished(task="embed")
    metrics.request_finished(task="embed")

    assert metrics.in_flight(task="embed") == 0
    assert metrics.max_concurrency(task="embed") == 2


def test_structured_event_keeps_only_safe_typed_fields() -> None:
    event = StructuredEvent(
        name="model.request.completed",
        correlation_id="corr-1",
        task="answer_generate",
        model="profile-v1",
        attempt=2,
        duration_ms=12.5,
        input_count=3,
        output_count=1,
        result="success",
        reason_code=None,
    )

    assert event.as_dict() == {
        "name": "model.request.completed",
        "correlation_id": "corr-1",
        "task": "answer_generate",
        "model": "profile-v1",
        "attempt": 2,
        "duration_ms": 12.5,
        "input_count": 3,
        "output_count": 1,
        "result": "success",
    }


@pytest.mark.parametrize("field,value", [("attempt", 0), ("duration_ms", -1.0), ("input_count", -1)])
def test_structured_event_rejects_invalid_measurements(field: str, value: object) -> None:
    fields = {
        "name": "model.request.completed",
        "correlation_id": "corr-1",
        "task": "answer_generate",
        "model": "profile-v1",
        "attempt": 1,
        "duration_ms": 1.0,
        "input_count": 0,
        "output_count": 0,
        "result": "success",
    }
    fields[field] = value

    with pytest.raises(ValueError, match=field):
        StructuredEvent(**fields)


def test_in_memory_sink_preserves_event_order_without_payload_or_secret_fields() -> None:
    sink = InMemoryEventSink()
    sink.emit(
        StructuredEvent(
            name="model.request.failed",
            correlation_id="corr-2",
            task="pdf_extract",
            model="profile-v1",
            attempt=1,
            duration_ms=3.0,
            input_count=1,
            output_count=0,
            result="failure",
            reason_code="timeout",
        )
    )

    assert sink.events[0].as_dict()["reason_code"] == "timeout"
    assert "input" not in sink.events[0].as_dict()
    assert "response" not in sink.events[0].as_dict()
    assert "api_key" not in sink.events[0].as_dict()


def test_logging_sink_emits_allowlisted_event_fields_without_payload(caplog) -> None:
    sink = LoggingEventSink(logging.getLogger("saxophone.test.observability"))
    event = StructuredEvent(
        name="model.request.failed",
        correlation_id="corr-3",
        task="answer_generate",
        model="profile-v1",
        attempt=2,
        duration_ms=8.0,
        input_count=2,
        output_count=0,
        result="failure",
        reason_code="timeout",
    )

    with caplog.at_level(logging.INFO, logger="saxophone.test.observability"):
        sink.emit(event)

    record = caplog.records[0]
    assert record.message == "model.request.failed"
    assert record.structured_event == event.as_dict()
    assert "input" not in record.structured_event
    assert "response" not in record.structured_event
    assert "api_key" not in record.structured_event
