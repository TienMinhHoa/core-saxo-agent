"""LangChain tool adapters for the typed document and web search ports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from .contracts import AgentQuestion, RunBudget, WebSearchResult
from .document_search import DocumentSearchResult

_BUDGET_INPUT_KEY = "budget"
_BUDGET_CONFIG_KEY = "_saxophone_agent_budget"


class AgentToolInput(BaseModel):
    """JSON-safe arguments exposed to the model-facing tool schema."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    filters: dict[str, str] = Field(default_factory=dict)
    context_limit: int = Field(default=12_000, gt=0)


class _BudgetAwareLangChainTool(BaseTool):
    """Base tool that keeps the mutable run budget outside the public schema."""

    args_schema: ClassVar[type[BaseModel]] = AgentToolInput
    model_config = ConfigDict(arbitrary_types_allowed=True)
    adapter: object = Field(exclude=True, repr=False)

    def __init__(self, adapter: object, **kwargs: Any) -> None:
        if not callable(getattr(adapter, "search", None)):
            raise TypeError("adapter must provide async search")
        super().__init__(adapter=adapter, **kwargs)

    async def ainvoke(
        self,
        input: object,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> object:
        """Invoke the real LangChain tool while carrying the typed budget runtime-only."""

        payload = dict(input) if isinstance(input, Mapping) else input
        budget = None
        if isinstance(payload, dict):
            budget = payload.pop(_BUDGET_INPUT_KEY, None)
        merged_config = _with_budget(config, budget)
        return await super().ainvoke(payload, config=merged_config, **kwargs)

    async def search(self, question: AgentQuestion, budget: RunBudget) -> object:
        """Expose the domain port shape without bypassing LangChain callbacks."""

        if not isinstance(question, AgentQuestion):
            raise TypeError("question must be an AgentQuestion")
        if not isinstance(budget, RunBudget):
            raise TypeError("budget must be a RunBudget")
        return await self.ainvoke(
            {
                "question": question.question,
                "filters": dict(question.filters),
                "context_limit": question.context_limit,
                _BUDGET_INPUT_KEY: budget,
            }
        )

    def _run(self, *_args: object, **_kwargs: object) -> object:
        raise RuntimeError("search tools are async-only; use ainvoke")


class DocumentSearchLangChainTool(_BudgetAwareLangChainTool):
    """LangChain wrapper around the typed document-search adapter."""

    name: str = "document_search"
    description: str = (
        "Search the indexed documents and return typed paragraph and relation candidates."
    )

    async def _arun(
        self,
        question: str,
        filters: dict[str, str],
        context_limit: int,
        *,
        config: RunnableConfig,
    ) -> DocumentSearchResult:
        budget = _budget_from_config(config)
        request = AgentQuestion(question, filters=filters, context_limit=context_limit)
        result = await self.adapter.search(request, budget)  # type: ignore[attr-defined]
        if not isinstance(result, DocumentSearchResult):
            raise TypeError("document search adapter must return DocumentSearchResult")
        return result


class WebSearchLangChainTool(_BudgetAwareLangChainTool):
    """LangChain wrapper around the typed web-search adapter."""

    name: str = "web_search"
    description: str = "Search external sources and return normalized web evidence."

    async def _arun(
        self,
        question: str,
        filters: dict[str, str],
        context_limit: int,
        *,
        config: RunnableConfig,
    ) -> WebSearchResult:
        budget = _budget_from_config(config)
        request = AgentQuestion(question, filters=filters, context_limit=context_limit)
        result = await self.adapter.search(request, budget)  # type: ignore[attr-defined]
        if not isinstance(result, WebSearchResult):
            raise TypeError("web search adapter must return WebSearchResult")
        return result


def create_document_search_tool(adapter: object) -> DocumentSearchLangChainTool:
    """Build the model-facing document-search tool for one typed adapter."""

    return DocumentSearchLangChainTool(adapter=adapter)


def create_web_search_tool(adapter: object) -> WebSearchLangChainTool:
    """Build the model-facing web-search tool for one typed adapter."""

    return WebSearchLangChainTool(adapter=adapter)


def _with_budget(
    config: RunnableConfig | None,
    budget: object,
) -> RunnableConfig:
    merged: RunnableConfig = dict(config or {})
    configurable = merged.get("configurable")
    normalized = dict(configurable) if isinstance(configurable, Mapping) else {}
    normalized[_BUDGET_CONFIG_KEY] = budget
    merged["configurable"] = normalized
    return merged


def _budget_from_config(config: RunnableConfig) -> RunBudget:
    configurable = config.get("configurable")
    budget = configurable.get(_BUDGET_CONFIG_KEY) if isinstance(configurable, Mapping) else None
    if not isinstance(budget, RunBudget):
        raise TypeError("tool invocation requires a RunBudget")
    return budget


__all__ = [
    "AgentToolInput",
    "DocumentSearchLangChainTool",
    "WebSearchLangChainTool",
    "create_document_search_tool",
    "create_web_search_tool",
]
