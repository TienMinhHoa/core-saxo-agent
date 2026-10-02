"""Budget-aware normalization for external web-search providers.

The provider boundary deliberately accepts provider-shaped values.  This
adapter is the only place that maps those values into the immutable
``WebSearchResult`` contract consumed by the agent graph.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .contracts import AgentQuestion, RunBudget, WebSearchItem, WebSearchResult
from .policies import run_with_budget


class WebSearchProvider(Protocol):
    """Minimal async provider contract used by the agent adapter."""

    async def search(self, query: str, *, limit: int) -> object:
        """Return provider-shaped search results for one query."""


class WebSearchQueryPlan(BaseModel):
    """Provider-neutral query plan produced by the search subagent."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1)
    interpretation: str = Field(default="", max_length=500)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class WebSearchQueryPlanner:
    """Use a structured model to turn an underspecified request into a search query."""

    def __init__(self, provider: object, *, domain_context: str = "") -> None:
        if not callable(getattr(provider, "generate_structured", None)):
            raise TypeError("provider must provide generate_structured")
        self._provider = provider
        self._domain_context = domain_context.strip()

    async def plan(self, question: AgentQuestion) -> WebSearchQueryPlan:
        if not isinstance(question, AgentQuestion):
            raise ValueError("question must be an AgentQuestion")
        context = self._domain_context or "Infer the relevant subject area from the request."
        result = await self._provider.generate_structured(
            task_type="web_search_query_planning",
            system_prompt=(
                "You are a general-purpose web search query planning subagent. "
                "Rewrite the user's request into one precise search query. "
                "Preserve important names, symbols, numbers, and quoted terms. "
                "Resolve shorthand only when context supports it; otherwise keep "
                "the ambiguity visible in the query. Do not answer the question, "
                "do not invent facts, and do not hardcode a domain glossary. "
                f"Subject context: {context}"
            ),
            user_prompt=f"User request:\n{question.question}\nFilters: {dict(question.filters)}",
            response_model=WebSearchQueryPlan,
        )
        return result if isinstance(result, WebSearchQueryPlan) else WebSearchQueryPlan.model_validate(result)


class WebSearchAdapter:
    """Normalize one provider response behind the shared web-search port."""

    name = RunBudget.WEB_SEARCH

    def __init__(
        self,
        provider: WebSearchProvider,
        *,
        max_results: int = 10,
        max_content_chars: int = 4_000,
        clock: Callable[[], str] | None = None,
        query_planner: object | None = None,
    ) -> None:
        search = getattr(provider, "search", None)
        if not callable(search):
            raise TypeError("provider must provide search")
        if (
            isinstance(max_results, bool)
            or not isinstance(max_results, int)
            or max_results < 1
        ):
            raise ValueError("max_results must be a positive integer")
        if (
            isinstance(max_content_chars, bool)
            or not isinstance(max_content_chars, int)
            or max_content_chars < 1
        ):
            raise ValueError("max_content_chars must be a positive integer")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        self._provider = provider
        self._max_results = max_results
        self._max_content_chars = max_content_chars
        self._clock = clock or _utc_now
        if query_planner is not None and not callable(getattr(query_planner, "plan", None)):
            raise TypeError("query_planner must provide plan")
        self._query_planner = query_planner

    async def search(
        self,
        question: AgentQuestion,
        budget: RunBudget,
    ) -> WebSearchResult:
        """Run and normalize a provider call under the shared run budget."""

        if not isinstance(question, AgentQuestion):
            raise ValueError("question must be an AgentQuestion")
        if not isinstance(budget, RunBudget):
            raise TypeError("budget must be a RunBudget")
        return await run_with_budget(
            budget,
            self.name,
            lambda: self._search_and_normalize(question, budget),
        )

    async def run(self, request: object, budget: RunBudget) -> WebSearchResult:
        """Expose the common named-tool shape used by the agent registry."""

        if not isinstance(request, AgentQuestion):
            raise ValueError("request must be an AgentQuestion")
        return await self.search(request, budget)

    async def _search_and_normalize(
        self,
        question: AgentQuestion,
        budget: RunBudget,
    ) -> WebSearchResult:
        limit = min(self._max_results, budget.max_hits_per_tool)
        query = question.question
        if self._query_planner is not None:
            try:
                plan = self._query_planner.plan(question)
                if inspect.isawaitable(plan):
                    plan = await plan
                planned_query = getattr(plan, "query", None)
                if isinstance(planned_query, str) and planned_query.strip():
                    query = planned_query.strip()
            except Exception:
                query = question.question
        response = self._provider.search(query, limit=limit)
        if inspect.isawaitable(response):
            response = await response
        else:
            raise TypeError("provider.search must return an awaitable")
        return self._normalize_response(query, response, limit=limit)

    def _normalize_response(
        self,
        query: str,
        response: object,
        *,
        limit: int,
    ) -> WebSearchResult:
        if response is None:
            return WebSearchResult(query=query, status="no_results")

        raw_items, raw_status = _extract_items(response)
        items = tuple(self._normalize_item(item) for item in tuple(raw_items)[:limit])
        status = _normalize_status(raw_status, has_items=bool(items))
        return WebSearchResult(query=query, items=items, status=status)

    def _normalize_item(self, raw_item: object) -> WebSearchItem:
        if isinstance(raw_item, WebSearchItem):
            if len(raw_item.content) <= self._max_content_chars:
                return raw_item
            return WebSearchItem(
                title=raw_item.title,
                url=raw_item.url,
                snippet=raw_item.snippet,
                content=raw_item.content[: self._max_content_chars],
                retrieved_at=raw_item.retrieved_at,
            )

        title = _required_field(raw_item, "title")
        url = _required_field(raw_item, "url")
        content = _optional_field(raw_item, "content")
        snippet = _optional_field(raw_item, "snippet") or content
        if not snippet:
            raise ValueError("web result snippet must not be blank")
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise ValueError("web result content must be a string")
        retrieved_at = _optional_field(raw_item, "retrieved_at") or self._clock()
        if not isinstance(retrieved_at, str) or not retrieved_at.strip():
            raise ValueError("web result retrieved_at must not be blank")
        return WebSearchItem(
            title=title,
            url=url,
            snippet=snippet[: self._max_content_chars],
            content=content[: self._max_content_chars],
            retrieved_at=retrieved_at,
        )


def _extract_items(response: object) -> tuple[Sequence[object], object | None]:
    if isinstance(response, WebSearchResult):
        return response.items, response.status
    if isinstance(response, Mapping):
        raw_items = response.get(
            "items", response.get("results", response.get("data", ()))
        )
        status = response.get("status")
    else:
        raw_items = getattr(response, "items", getattr(response, "results", response))
        status = getattr(response, "status", None)
    if isinstance(raw_items, (str, bytes)) or not isinstance(raw_items, Sequence):
        raise ValueError("web provider results must be a sequence")
    return tuple(raw_items), status


def _required_field(value: object, name: str) -> object:
    result = _optional_field(value, name)
    if result is None or (isinstance(result, str) and not result.strip()):
        raise ValueError(f"web result {name} must not be blank")
    return result


def _optional_field(value: object, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _normalize_status(value: object, *, has_items: bool) -> str:
    if value is None:
        return "ready" if has_items else "no_results"
    if not isinstance(value, str) or not value.strip():
        raise ValueError("web result status must be a non-blank string")
    return value.strip()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


WebSearchToolAdapter = WebSearchAdapter
WebSearchService = WebSearchAdapter


__all__ = [
    "WebSearchAdapter",
    "WebSearchProvider",
    "WebSearchService",
    "WebSearchToolAdapter",
    "WebSearchQueryPlan",
    "WebSearchQueryPlanner",
]
