"""LangChain callback bridge for safe, public agent progress events."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from .events import AgentEvent, AgentEventSink, AgentEventType

_PUBLIC_TAGS = frozenset({"answer", "public_answer", "synthesis"})
_STAGE_ALIASES = (
    ("document_search", "document_search"),
    ("web_search", "web_search"),
    ("select_evidence", "selection"),
    ("selection", "selection"),
    ("synthesis", "synthesis"),
    ("answer", "synthesis"),
    ("validate", "validation"),
    ("understanding", "understanding"),
    ("evaluate", "understanding"),
    ("receive", "understanding"),
)


class AgentEventCallbackHandler(AsyncCallbackHandler):
    """Map LangChain lifecycle callbacks to the allowlisted AgentEvent DTO.

    The handler deliberately ignores callback payloads such as prompts,
    tool inputs, model outputs, and exception messages. Public answer deltas
    require an explicit ``answer``/``public_answer``/``synthesis`` tag (or
    ``metadata={"stream_public": True}``) so private model work is not sent
    to an SSE client by accident.
    """

    def __init__(
        self,
        *,
        run_id: str,
        sink: AgentEventSink,
        emit_run_failures: bool = False,
    ) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be non-blank")
        if not callable(getattr(sink, "publish", None)):
            raise TypeError("sink must provide async publish")
        if not isinstance(emit_run_failures, bool):
            raise TypeError("emit_run_failures must be a boolean")
        self.run_id = run_id.strip()
        self._sink = sink
        self._emit_run_failures = emit_run_failures
        self._started_stages: set[str] = set()
        self._tool_names: dict[str, str] = {}
        self._public_llm_runs: set[str] = set()
        self._synthesis_started = False

    async def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        del inputs, parent_run_id, kwargs
        stage = _stage_name(serialized, tags=tags, metadata=metadata)
        if stage is None or stage in self._started_stages:
            return
        self._started_stages.add(stage)
        await self._publish(AgentEvent(AgentEventType.STAGE_STARTED, self.run_id, stage=stage))

    async def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        del run_id, parent_run_id, kwargs
        if not isinstance(outputs, Mapping):
            return
        action = _safe_label(outputs.get("decision"))
        reason_code = _safe_label(outputs.get("reason_code"))
        if action is None or reason_code is None:
            return
        await self._publish(
            AgentEvent(
                AgentEventType.DECISION,
                self.run_id,
                action=action,
                reason_code=reason_code,
            )
        )

    async def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        del error, run_id, parent_run_id, kwargs
        if self._emit_run_failures:
            await self._publish(
                AgentEvent(
                    AgentEventType.RUN_FAILED,
                    self.run_id,
                    error_code="chain_error",
                )
            )

    async def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        del input_str, parent_run_id, tags, metadata, inputs, kwargs
        callback_id = str(run_id)
        tool = _tool_name(serialized)
        self._tool_names[callback_id] = tool
        await self._publish(
            AgentEvent(
                AgentEventType.TOOL_STARTED,
                self.run_id,
                tool=tool,
                call_id=callback_id,
            )
        )

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        del output, parent_run_id, kwargs
        callback_id = str(run_id)
        tool = self._tool_names.pop(callback_id, "tool")
        await self._publish(
            AgentEvent(
                AgentEventType.TOOL_COMPLETED,
                self.run_id,
                tool=tool,
                call_id=callback_id,
                status="completed",
            )
        )

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        del parent_run_id, kwargs
        callback_id = str(run_id)
        tool = self._tool_names.pop(callback_id, "tool")
        await self._publish(
            AgentEvent(
                AgentEventType.TOOL_COMPLETED,
                self.run_id,
                tool=tool,
                call_id=callback_id,
                status="failed",
                error_code=_safe_error_code(error),
            )
        )

    async def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        del serialized, prompts, parent_run_id, kwargs
        if not _is_public_output(tags=tags, metadata=metadata):
            return
        self._public_llm_runs.add(str(run_id))
        if self._synthesis_started:
            return
        self._synthesis_started = True
        await self._publish(AgentEvent(AgentEventType.SYNTHESIS_STARTED, self.run_id))

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any] | None,
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        del messages
        await self.on_llm_start(
            serialized,
            [],
            run_id=run_id,
            parent_run_id=parent_run_id,
            tags=tags,
            metadata=metadata,
            **kwargs,
        )

    async def on_llm_new_token(
        self,
        token: str | list[str | dict[str, Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        del parent_run_id, kwargs
        callback_id = str(run_id)
        if callback_id not in self._public_llm_runs:
            return
        if tags and not _is_public_output(tags=tags, metadata=None):
            return
        text = _public_token(token)
        if text is None:
            return
        await self._publish(
            AgentEvent(AgentEventType.ANSWER_DELTA, self.run_id, text=text[:4096])
        )

    async def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        del response, parent_run_id, tags, kwargs
        self._public_llm_runs.discard(str(run_id))

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        del error, parent_run_id, tags, kwargs
        self._public_llm_runs.discard(str(run_id))

    async def _publish(self, event: AgentEvent) -> None:
        try:
            await self._sink.publish(event)
        except (KeyError, TypeError, ValueError):
            # A disconnected or already-closed run must not break the model call.
            return


def _stage_name(
    serialized: Mapping[str, Any] | None,
    *,
    tags: Sequence[str] | None,
    metadata: Mapping[str, Any] | None,
) -> str | None:
    candidates: list[str] = []
    if metadata is not None:
        value = metadata.get("langgraph_node")
        if isinstance(value, str):
            candidates.append(value)
    for tag in tags or ():
        if isinstance(tag, str) and tag.startswith("langgraph_node:"):
            candidates.append(tag.split(":", 1)[1])
    name = serialized.get("name") if isinstance(serialized, Mapping) else None
    if isinstance(name, str):
        candidates.append(name)
    for candidate in candidates:
        normalized = candidate.strip().lower()
        for alias, stage in _STAGE_ALIASES:
            if alias in normalized:
                return stage
    return None


def _tool_name(serialized: Mapping[str, Any] | None) -> str:
    name = serialized.get("name") if isinstance(serialized, Mapping) else None
    if not isinstance(name, str):
        identifier = serialized.get("id") if isinstance(serialized, Mapping) else None
        if isinstance(identifier, Sequence) and not isinstance(identifier, (str, bytes)):
            name = identifier[-1] if identifier else None
    return _safe_label(name) or "tool"


def _safe_label(value: object) -> str | None:
    if hasattr(value, "value"):
        value = getattr(value, "value")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 64:
        return None
    if any(not (character.isalnum() or character in "_.:-") for character in normalized):
        return None
    return normalized


def _is_public_output(
    *,
    tags: Sequence[str] | None,
    metadata: Mapping[str, Any] | None,
) -> bool:
    normalized_tags = {tag.strip().lower() for tag in tags or () if isinstance(tag, str)}
    return bool(normalized_tags & _PUBLIC_TAGS) or bool(
        metadata is not None and metadata.get("stream_public") is True
    )


def _public_token(token: object) -> str | None:
    if isinstance(token, str):
        return token
    if isinstance(token, list) and all(isinstance(item, str) for item in token):
        return "".join(token)
    return None


def _safe_error_code(error: BaseException) -> str:
    return _safe_label(error.__class__.__name__) or "tool_error"


__all__ = ["AgentEventCallbackHandler"]
