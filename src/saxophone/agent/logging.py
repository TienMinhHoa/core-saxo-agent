"""Safe, structured logging for one Main Agent run."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import logging
import json
from time import perf_counter
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from .langchain_callbacks import _safe_error_code

CHAT_LOGGER_NAME = "saxophone.chat"
_MAX_PREVIEW = 512


class AgentLoggingCallbackHandler(AsyncCallbackHandler):
    """Log graph and tool lifecycle events without logging their payloads."""

    def __init__(self, *, run_id: str, logger: logging.Logger | None = None) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be non-blank")
        self.run_id = run_id.strip()
        self.logger = logger or logging.getLogger(CHAT_LOGGER_NAME)
        self._started: dict[str, tuple[str, float]] = {}

    async def on_chat_model_start(self, *args: Any, **kwargs: Any) -> None:
        """Accept model-start callbacks without invoking LangChain's stub."""

        del args, kwargs

    async def on_llm_end(self, *args: Any, **kwargs: Any) -> None:
        """Keep model completion callbacks from affecting agent execution."""

        del args, kwargs

    async def on_llm_error(self, *args: Any, **kwargs: Any) -> None:
        """Keep the provider exception as the error that reaches the graph."""

        del args, kwargs

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
        callback_id = str(run_id)
        node = _node_name(serialized, tags=tags, metadata=metadata)
        self._started[callback_id] = (node, perf_counter())

    async def on_chain_end(
        self,
        outputs: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        del parent_run_id, kwargs
        callback_id = str(run_id)
        node, started = self._started.pop(callback_id, ("chain", perf_counter()))
        summary = _summarize_step(outputs)
        if _is_failed_step(outputs):
            failed_payload = {
                "event": "agent.step.failed",
                "run_id": self.run_id,
                "node": node,
                "duration_ms": _duration_ms(started),
                "error_code": _safe_error_code(
                    RuntimeError(str(outputs.get("error", "agent step failed")))
                ),
            }
            if isinstance(outputs, Mapping):
                for field in ("stage", "reason_code"):
                    value = outputs.get(field)
                    if value is not None:
                        failed_payload[field] = _enum_value(value)
            self._emit(
                logging.ERROR,
                failed_payload,
            )
            return
        if not summary:
            if self.logger.isEnabledFor(logging.DEBUG):
                preview = _answer_preview(outputs)
                if preview is not None:
                    self._emit(
                        logging.DEBUG,
                        {
                            "event": "agent.step.debug",
                            "run_id": self.run_id,
                            "node": node,
                            "duration_ms": _duration_ms(started),
                            "answer_preview": preview,
                        },
                    )
            return
        payload = {
            "event": "agent.step.completed",
            "run_id": self.run_id,
            "node": node,
            "duration_ms": _duration_ms(started),
        }
        payload.update(summary)
        self._emit(logging.INFO, payload)
        if self.logger.isEnabledFor(logging.DEBUG):
            preview = _answer_preview(outputs)
            if preview is not None:
                self._emit(logging.DEBUG, {**payload, "answer_preview": preview})

    async def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        del parent_run_id, kwargs
        callback_id = str(run_id)
        node, started = self._started.pop(callback_id, ("chain", perf_counter()))
        self._emit(
            logging.ERROR,
            {
                "event": "agent.step.failed",
                "run_id": self.run_id,
                "node": node,
                "duration_ms": _duration_ms(started),
                "error_code": _safe_error_code(error),
            },
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
        tool = _node_name(serialized, tags=None, metadata=None)
        self._started[callback_id] = (tool, perf_counter())
        self._emit(
            logging.INFO,
            {"event": "agent.tool.started", "run_id": self.run_id, "tool": tool},
        )

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        del parent_run_id, kwargs
        callback_id = str(run_id)
        tool, started = self._started.pop(callback_id, ("tool", perf_counter()))
        payload = {
            "event": "agent.tool.completed",
            "run_id": self.run_id,
            "tool": tool,
            "duration_ms": _duration_ms(started),
        }
        payload.update(_summarize_tool(output))
        self._emit(logging.INFO, payload)

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
        tool, started = self._started.pop(callback_id, ("tool", perf_counter()))
        self._emit(
            logging.ERROR,
            {
                "event": "agent.tool.failed",
                "run_id": self.run_id,
                "tool": tool,
                "duration_ms": _duration_ms(started),
                "error_code": _safe_error_code(error),
            },
        )

    def _emit(self, level: int, payload: dict[str, object]) -> None:
        self.logger.log(level, str(payload["event"]), extra={"chat_event": payload})


def log_agent_run_started(*, run_id: str, question: object, budget: object) -> None:
    _emit(
        logging.INFO,
        {
            "event": "agent.run.started",
            "run_id": run_id,
            "filter_count": len(getattr(question, "filters", ())),
            "context_limit": getattr(question, "context_limit", None),
            "max_document_search_calls": getattr(budget, "max_document_search_calls", None),
            "max_web_search_calls": getattr(budget, "max_web_search_calls", None),
        },
    )


def log_agent_run_completed(*, run_id: str, result: object) -> None:
    synthesis = getattr(result, "synthesis", None)
    ledger = getattr(result, "ledger", None)
    _emit(
        logging.INFO,
        {
            "event": "agent.run.completed",
            "run_id": run_id,
            "outcome": _enum_value(getattr(result, "outcome", None)),
            "stage": _enum_value(getattr(result, "stage", None)),
            "answer_chars": len(getattr(result, "answer", "") or ""),
            "source_count": len(getattr(ledger, "evidence", ()) or ()),
            "citation_count": len(getattr(synthesis, "citations", ()) or ()),
            "evidence_sufficient": getattr(synthesis, "evidence_sufficient", None),
            "budget_exhausted": getattr(ledger, "budget_exhausted", False),
            "budget_reason": getattr(ledger, "budget_reason", None),
            "used_tool_calls": _snapshot_value(result, "used_tool_calls"),
            "used_document_search_calls": _snapshot_value(result, "document_search_calls"),
            "used_web_search_calls": _snapshot_value(result, "web_search_calls"),
        },
    )


def log_agent_run_failed(*, run_id: str, error: object, result: object | None = None) -> None:
    safe_error = error if isinstance(error, BaseException) else RuntimeError("agent failed")
    _emit(
        logging.ERROR,
        {
            "event": "agent.run.failed",
            "run_id": run_id,
            "error_code": _safe_error_code(safe_error),
            "outcome": _enum_value(getattr(result, "outcome", None)) if result is not None else None,
        },
    )


def log_agent_run_cancelled(*, run_id: str) -> None:
    _emit(logging.WARNING, {"event": "agent.run.cancelled", "run_id": run_id})


def log_chat_request(*, run_id: str, route: str, request: object) -> None:
    _emit(
        logging.INFO,
        {
            "event": "chat.request.received",
            "run_id": run_id,
            "route": route,
            "filter_count": len(getattr(request, "filters", {}) or {}),
            "chunk_limit": getattr(request, "chunk_limit", None),
            "max_paragraphs": getattr(request, "max_paragraphs", None),
            "max_tokens": getattr(request, "max_tokens", None),
        },
    )


def log_chat_response(*, run_id: str, route: str, payload: Mapping[str, object]) -> None:
    _emit(
        logging.INFO,
        {
            "event": "chat.response.completed",
            "run_id": run_id,
            "route": route,
            "status": payload.get("status"),
            "answer_chars": len(payload.get("answer") or ""),
            "source_count": len(payload.get("sources") or ()),
        },
    )


def log_chat_failure(*, run_id: str, route: str, error: BaseException) -> None:
    _emit(
        logging.ERROR,
        {
            "event": "chat.request.failed",
            "run_id": run_id,
            "route": route,
            "error_code": _safe_error_code(error),
        },
    )


def _emit(level: int, payload: dict[str, object]) -> None:
    logging.getLogger(CHAT_LOGGER_NAME).log(
        level,
        str(payload["event"]),
        extra={"chat_event": {key: value for key, value in payload.items() if value is not None}},
    )


def _node_name(
    serialized: Mapping[str, Any] | None,
    *,
    tags: Sequence[str] | None,
    metadata: Mapping[str, Any] | None,
) -> str:
    values: list[object] = []
    if metadata:
        values.append(metadata.get("langgraph_node"))
    values.extend(tags or ())
    if serialized:
        values.append(serialized.get("name"))
    for value in values:
        if not isinstance(value, str):
            continue
        value = value.split(":", 1)[-1].strip()
        if value:
            return value[:80]
    return "chain"


def _summarize_step(outputs: object) -> dict[str, object]:
    if not isinstance(outputs, Mapping):
        return {}
    payload: dict[str, object] = {}
    result = outputs.get("document_result")
    if result is not None:
        hits = _sequence(getattr(result, "hits", ()))
        paragraphs = _sequence(getattr(result, "paragraph_candidates", ()))
        payload.update(
            {
                "hit_count": len(hits),
                "chunk_ids": [getattr(hit, "chunk_ref", "") for hit in hits],
                "paragraph_count": len(paragraphs),
                "paragraph_refs": [getattr(item, "paragraph_ref", "") for item in paragraphs],
                "confidence": getattr(result, "confidence", None),
                "search_status": _enum_value(getattr(result, "status", None)),
            }
        )
    selection = outputs.get("selection_result")
    if selection is not None:
        context = getattr(selection, "answer_context", None)
        refs = getattr(selection, "selected_paragraph_refs", ())
        payload.update(
            {
                "selection_strategy": _enum_value(getattr(selection, "strategy", None)),
                "selected_paragraph_refs": list(refs),
            }
        )
    if outputs.get("selection_strategy") is not None:
        payload["selection_strategy"] = _enum_value(outputs["selection_strategy"])
    web = outputs.get("web_result")
    if web is not None:
        items = _sequence(getattr(web, "items", ()))
        payload.update(
            {
                "result_count": len(items),
                "source_urls": [getattr(item, "url", "") for item in items],
            }
        )
    synthesis = outputs.get("synthesis_result")
    if synthesis is not None:
        payload.update(
            {
                "citation_count": len(getattr(synthesis, "citations", ()) or ()),
                "answer_chars": len(outputs.get("answer", "") or ""),
                "evidence_sufficient": getattr(synthesis, "evidence_sufficient", None),
            }
        )
    for field in ("stage", "decision", "outcome", "reason_code", "budget_exhausted", "budget_reason", "needs_web_fallback", "required_search_tool"):
        if outputs.get(field) is not None:
            payload[field] = _enum_value(outputs[field])
    return {key: value for key, value in payload.items() if value is not None}


def _is_failed_step(outputs: object) -> bool:
    if not isinstance(outputs, Mapping):
        return False
    outcome = _enum_value(outputs.get("outcome"))
    decision = _enum_value(outputs.get("decision"))
    return outcome == "failed" or decision == "failed"


def _summarize_tool(output: object) -> dict[str, object]:
    content = getattr(output, "content", output)
    if isinstance(content, str):
        try:
            output = json.loads(content)
        except (ValueError, TypeError):
            pass
    hits = getattr(output, "hits", None)
    if hits is None and isinstance(output, Mapping):
        for key in ("hits", "items", "results", "candidates", "selected_context_ids"):
            if key in output:
                hits = output[key]
                break
    values = _sequence(hits)
    summary: dict[str, object] = {"result_count": len(values)}
    if isinstance(output, Mapping):
        for name in ("remaining_document_search_calls", "remaining_web_search_calls", "remaining_context_tokens"):
            value = output.get(name)
            if type(value) is int and value >= 0:
                summary[name] = value
        if output.get("status") == "quota_exhausted":
            summary["quota_exhausted"] = True
        if output.get("status") in {"document_search_required_first", "web_only_requested"}:
            summary["source_policy_rejected"] = True
    return summary


def _answer_preview(outputs: object) -> str | None:
    if not isinstance(outputs, Mapping):
        return None
    answer = outputs.get("answer")
    if not isinstance(answer, str) or not answer:
        return None
    return answer[:_MAX_PREVIEW]


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()


def _duration_ms(started: float) -> float:
    return round(max(0.0, (perf_counter() - started) * 1000), 3)


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def _snapshot_value(result: object, name: str) -> object | None:
    snapshot = getattr(getattr(result, "budget", None), "snapshot", None)
    if not callable(snapshot):
        return None
    return getattr(snapshot(), name, None)


__all__ = [
    "AgentLoggingCallbackHandler",
    "CHAT_LOGGER_NAME",
    "log_agent_run_cancelled",
    "log_agent_run_completed",
    "log_agent_run_failed",
    "log_agent_run_started",
    "log_chat_failure",
    "log_chat_request",
    "log_chat_response",
]
