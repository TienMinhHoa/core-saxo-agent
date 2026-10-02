"""Safe, typed progress events emitted by one agent run."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Protocol


class AgentEventType(StrEnum):
    """Public event names used by the JSON and SSE boundaries."""

    RUN_STARTED = "run_started"
    STAGE_STARTED = "stage_started"
    TOOL_STARTED = "tool_started"
    TOOL_PROGRESS = "tool_progress"
    TOOL_COMPLETED = "tool_completed"
    DECISION = "decision"
    THINKING = "thinking"
    SYNTHESIS_STARTED = "synthesis_started"
    ANSWER_DELTA = "answer_delta"
    RUN_COMPLETED = "run_completed"
    RUN_RESULT = "run_result"
    RUN_FAILED = "run_failed"


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """Allowlisted event DTO that cannot carry hidden provider payloads.

    Event variants share one immutable shape so adapters can serialize them
    without passing arbitrary dictionaries through the orchestration layer.
    ``sequence`` is assigned by :class:`AgentRunManager` and is omitted from
    unsequenced payloads.
    """

    type: AgentEventType | str
    run_id: str
    sequence: int = 0
    stage: str | None = None
    tool: str | None = None
    call_id: str | None = None
    action: str | None = None
    reason_code: str | None = None
    status: str | None = None
    text: str | None = None
    error_code: str | None = None
    query_count: int | None = None
    completed: int | None = None
    total: int | None = None
    hit_count: int | None = None
    result_count: int | None = None
    confidence: float | None = None
    result: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        try:
            event_type = AgentEventType(self.type)
        except (TypeError, ValueError) as error:
            raise ValueError("type must be a supported agent event") from error
        object.__setattr__(self, "type", event_type)

        run_id = _required_text("run_id", self.run_id)
        object.__setattr__(self, "run_id", run_id)
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise ValueError("sequence must be a non-negative integer")
        if self.sequence < 0:
            raise ValueError("sequence must be a non-negative integer")

        for field_name in (
            "stage",
            "tool",
            "call_id",
            "action",
            "reason_code",
            "status",
            "error_code",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _required_text(field_name, value))
        if self.text is not None and not isinstance(self.text, str):
            raise ValueError("text must be a string when provided")
        if self.result is not None:
            if not isinstance(self.result, Mapping):
                raise ValueError("result must be a mapping")
            object.__setattr__(self, "result", dict(self.result))

        for field_name in (
            "query_count",
            "completed",
            "total",
            "hit_count",
            "result_count",
        ):
            value = getattr(self, field_name)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"{field_name} must be a non-negative integer")
        if self.confidence is not None:
            if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
                raise ValueError("confidence must be a number between 0 and 1")
            if not 0 <= self.confidence <= 1:
                raise ValueError("confidence must be a number between 0 and 1")

        if self.type is AgentEventType.STAGE_STARTED:
            _require_event_field(self.stage, "stage")
        elif self.type is AgentEventType.TOOL_STARTED:
            _require_event_field(self.tool, "tool")
            _require_event_field(self.call_id, "call_id")
        elif self.type is AgentEventType.TOOL_PROGRESS:
            _require_event_field(self.tool, "tool")
            _require_event_field(self.call_id, "call_id")
            _require_event_field(self.completed, "completed")
            _require_event_field(self.total, "total")
            if self.completed > self.total:
                raise ValueError("completed must not exceed total")
        elif self.type is AgentEventType.TOOL_COMPLETED:
            _require_event_field(self.tool, "tool")
            _require_event_field(self.call_id, "call_id")
        elif self.type is AgentEventType.DECISION:
            _require_event_field(self.action, "action")
            _require_event_field(self.reason_code, "reason_code")
        elif self.type is AgentEventType.THINKING:
            if self.text is None:
                raise ValueError("thinking text must be a non-blank single line")
            normalized_text = self.text.strip()
            if not normalized_text or any(
                character in normalized_text for character in "\r\n"
            ):
                raise ValueError("thinking text must be a non-blank single line")
            object.__setattr__(self, "text", normalized_text)
        elif self.type is AgentEventType.ANSWER_DELTA:
            if self.text is None:
                raise ValueError("text is required")
        elif self.type is AgentEventType.RUN_COMPLETED:
            _require_event_field(self.status, "status")
        elif self.type is AgentEventType.RUN_FAILED:
            _require_event_field(self.error_code, "error_code")
        elif self.type is AgentEventType.RUN_RESULT:
            _require_event_field(self.result, "result")

    @property
    def terminal(self) -> bool:
        """Whether this event closes the run stream."""

        return self.type in {AgentEventType.RUN_COMPLETED, AgentEventType.RUN_FAILED}

    def as_dict(self) -> dict[str, object]:
        """Return the safe wire representation for JSON or SSE adapters."""

        payload: dict[str, object] = {
            "type": self.type.value,
            "run_id": self.run_id,
        }
        if self.sequence:
            payload["sequence"] = self.sequence
        for field_name in (
            "stage",
            "tool",
            "call_id",
            "action",
            "reason_code",
            "status",
            "text",
            "error_code",
            "query_count",
            "completed",
            "total",
            "hit_count",
            "result_count",
            "confidence",
        ):
            value = getattr(self, field_name)
            if value is not None:
                payload[field_name] = value
        if self.result is not None:
            payload["result"] = dict(self.result)
        return payload


class AgentEventSink(Protocol):
    """Async application port for publishing run-scoped events."""

    async def publish(self, event: AgentEvent) -> AgentEvent:
        """Publish an event and return its sequenced representation."""


def _required_text(field_name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-blank")
    return value.strip()


def _require_event_field(value: object, field_name: str) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{field_name} is required")


__all__ = ["AgentEvent", "AgentEventSink", "AgentEventType"]
