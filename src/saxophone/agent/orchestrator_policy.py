"""Model-backed routing policy for the Main Agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .state import AgentDecision, AgentGraphState, AgentStage


class OrchestratorRoute(BaseModel):
    """One validated command returned by the Main orchestrator."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["select", "web", "synthesize"] = Field(...)
    reason: str = Field(default="", max_length=500)


class ModelOrchestratorPolicy:
    """Ask the main model which child agent should run next."""

    def __init__(self, provider: object) -> None:
        if not callable(getattr(provider, "generate_structured", None)):
            raise TypeError("provider must provide generate_structured")
        self._provider = provider

    async def __call__(self, state: AgentGraphState) -> AgentDecision:
        stage = state.get("stage")
        prompt = _render_state(state)
        result = await self._provider.generate_structured(
            task_type="orchestrator_decision",
            system_prompt=(
                "You are the main orchestrator for a question answering agent. "
                "Choose exactly one next route from select, web, synthesize. "
                "At document evaluation, use select when local candidates may answer; "
                "use web when local search has no usable context. After selection, "
                "use web when selected evidence does not answer the question, otherwise "
                "use synthesize. After web search always use synthesize. Never answer "
                "the user and never invent evidence."
            ),
            user_prompt=prompt,
            response_model=OrchestratorRoute,
        )
        route = result if isinstance(result, OrchestratorRoute) else OrchestratorRoute.model_validate(result)
        if stage is AgentStage.WEB_SEARCHING:
            return AgentDecision.SYNTHESIZE
        return AgentDecision(route.decision)


def _render_state(state: AgentGraphState) -> str:
    question = state.get("question")
    result = state.get("document_result")
    selection = state.get("selection_result")
    web = state.get("web_result")
    payload: dict[str, object] = {
        "question": getattr(question, "question", ""),
        "stage": str(state.get("stage", "")),
    }
    if result is not None:
        payload["document"] = {
            "status": str(getattr(result, "status", "")),
            "hit_count": len(getattr(result, "hits", ()) or ()),
            "paragraph_count": len(getattr(result, "paragraph_candidates", ()) or ()),
            "confidence": getattr(result, "confidence", None),
        }
    if selection is not None:
        payload["selection"] = {
            "paragraph_refs": list(getattr(selection, "selected_paragraph_refs", ()) or ())
        }
    if web is not None:
        payload["web"] = {
            "status": getattr(web, "status", ""),
            "item_count": len(getattr(web, "items", ()) or ()),
        }
    return str(payload)


__all__ = ["ModelOrchestratorPolicy", "OrchestratorRoute"]
