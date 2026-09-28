"""In-process event queues for agent progress and SSE adapters."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from uuid import uuid4

from .events import AgentEvent, AgentEventType


@dataclass(slots=True)
class _RunState:
    history: list[AgentEvent] = field(default_factory=list)
    subscribers: set[asyncio.Queue[AgentEvent]] = field(default_factory=set)
    next_sequence: int = 1
    terminal: bool = False


class AgentRunManager:
    """Maintain ordered, replayable event streams for active agent runs."""

    def __init__(self, *, queue_size: int = 0) -> None:
        if isinstance(queue_size, bool) or not isinstance(queue_size, int) or queue_size < 0:
            raise ValueError("queue_size must be a non-negative integer")
        self._queue_size = queue_size
        self._runs: dict[str, _RunState] = {}
        self._lock = asyncio.Lock()

    async def start(self, run_id: str | None = None) -> str:
        """Create a run and publish its first ``run_started`` event."""

        normalized = _normalize_run_id(run_id or uuid4().hex)
        async with self._lock:
            if normalized in self._runs:
                raise ValueError("run_id is already active")
            state = _RunState()
            self._runs[normalized] = state
            self._append_locked(
                normalized,
                state,
                AgentEvent(AgentEventType.RUN_STARTED, run_id=normalized),
            )
        return normalized

    async def publish(self, event: AgentEvent) -> AgentEvent:
        """Append one event, assign its sequence, and notify subscribers."""

        if not isinstance(event, AgentEvent):
            raise TypeError("event must be an AgentEvent")
        async with self._lock:
            state = self._runs.get(event.run_id)
            if state is None:
                raise KeyError(f"unknown run: {event.run_id}")
            if state.terminal:
                raise ValueError("run has already reached a terminal state")
            sequenced, subscribers = self._append_locked(event.run_id, state, event)
        await self._notify(subscribers, sequenced)
        return sequenced

    async def emit(self, event: AgentEvent) -> AgentEvent:
        """Compatibility alias for sinks that use ``emit`` terminology."""

        return await self.publish(event)

    async def cancel(self, run_id: str, *, error_code: str = "client_disconnected") -> bool:
        """Close an active run with a safe failure event."""

        normalized = _normalize_run_id(run_id)
        async with self._lock:
            state = self._runs.get(normalized)
            if state is None:
                raise KeyError(f"unknown run: {normalized}")
            if state.terminal:
                return False
            event = AgentEvent(
                AgentEventType.RUN_FAILED,
                run_id=normalized,
                error_code=error_code,
            )
            sequenced, subscribers = self._append_locked(normalized, state, event)
        await self._notify(subscribers, sequenced)
        return True

    async def events(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
    ) -> AsyncIterator[AgentEvent]:
        """Yield history and live events, stopping after a terminal event."""

        normalized = _normalize_run_id(run_id)
        if isinstance(after_sequence, bool) or not isinstance(after_sequence, int):
            raise ValueError("after_sequence must be a non-negative integer")
        if after_sequence < 0:
            raise ValueError("after_sequence must be a non-negative integer")

        queue: asyncio.Queue[AgentEvent] | None = None
        async with self._lock:
            state = self._runs.get(normalized)
            if state is None:
                raise KeyError(f"unknown run: {normalized}")
            replay = tuple(event for event in state.history if event.sequence > after_sequence)
            terminal_in_replay = state.terminal and any(event.terminal for event in replay)
            if not terminal_in_replay:
                queue = asyncio.Queue(maxsize=self._queue_size)
                state.subscribers.add(queue)

        try:
            for event in replay:
                yield event
            if terminal_in_replay:
                return
            if queue is None:  # pragma: no cover - defensive invariant
                return
            while True:
                event = await queue.get()
                yield event
                if event.terminal:
                    return
        finally:
            if queue is not None:
                async with self._lock:
                    state = self._runs.get(normalized)
                    if state is not None:
                        state.subscribers.discard(queue)

    async def history(self, run_id: str) -> tuple[AgentEvent, ...]:
        """Return a detached event history for diagnostics and reconnects."""

        normalized = _normalize_run_id(run_id)
        async with self._lock:
            state = self._runs.get(normalized)
            if state is None:
                raise KeyError(f"unknown run: {normalized}")
            return tuple(state.history)

    async def is_active(self, run_id: str) -> bool:
        normalized = _normalize_run_id(run_id)
        async with self._lock:
            state = self._runs.get(normalized)
            if state is None:
                raise KeyError(f"unknown run: {normalized}")
            return not state.terminal

    @staticmethod
    def _append_locked(
        run_id: str,
        state: _RunState,
        event: AgentEvent,
    ) -> tuple[AgentEvent, tuple[asyncio.Queue[AgentEvent], ...]]:
        if event.run_id != run_id:
            raise ValueError("event run_id must match the active run")
        sequenced = replace(event, sequence=state.next_sequence)
        state.next_sequence += 1
        state.history.append(sequenced)
        if sequenced.terminal:
            state.terminal = True
        return sequenced, tuple(state.subscribers)

    @staticmethod
    async def _notify(
        subscribers: tuple[asyncio.Queue[AgentEvent], ...],
        event: AgentEvent,
    ) -> None:
        if not subscribers:
            return
        await asyncio.gather(*(subscriber.put(event) for subscriber in subscribers))


def _normalize_run_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("run_id must be non-blank")
    return value.strip()


__all__ = ["AgentRunManager"]
