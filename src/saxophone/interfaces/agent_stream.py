"""SSE serialization for the public agent progress event stream."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from saxophone.agent.events import AgentEvent
from saxophone.agent.streaming import AgentRunManager


def encode_agent_event(event: AgentEvent) -> str:
    """Encode one allowlisted event using the SSE wire format."""

    if not isinstance(event, AgentEvent):
        raise TypeError("event must be an AgentEvent")
    payload = json.dumps(
        event.as_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        f"id: {event.sequence}\n"
        f"event: {event.type.value}\n"
        f"data: {payload}\n\n"
    )


async def iter_agent_events(
    manager: AgentRunManager,
    run_id: str,
    *,
    after_sequence: int = 0,
) -> AsyncIterator[str]:
    """Yield replayable SSE frames from one managed run."""

    if not isinstance(manager, AgentRunManager):
        raise TypeError("manager must be an AgentRunManager")
    async for event in manager.events(run_id, after_sequence=after_sequence):
        yield encode_agent_event(event)


__all__ = ["encode_agent_event", "iter_agent_events"]
