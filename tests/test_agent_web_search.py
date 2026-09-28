from __future__ import annotations

import pytest

from saxophone.agent.contracts import AgentQuestion, RunBudget, WebSearchItem
from saxophone.agent.web_search import WebSearchAdapter


class _Provider:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, *, limit: int) -> object:
        self.calls.append((query, limit))
        return self.response


@pytest.mark.anyio
async def test_web_search_adapter_normalizes_results_and_applies_limits() -> None:
    provider = _Provider(
        {
            "results": [
                {
                    "title": "  Major triad  ",
                    "url": "https://example.test/triad",
                    "snippet": "A root, third, and fifth.",
                    "content": "A root, third, and fifth. Extra details.",
                },
                {
                    "title": "Ignored",
                    "url": "https://example.test/ignored",
                    "snippet": "This item is outside the configured cap.",
                },
            ]
        }
    )
    adapter = WebSearchAdapter(
        provider,
        max_results=1,
        max_content_chars=20,
        clock=lambda: "2026-09-29T10:00:00+00:00",
    )
    budget = RunBudget(max_hits_per_tool=5)

    result = await adapter.search(AgentQuestion("What is a major triad?"), budget)

    assert provider.calls == [("What is a major triad?", 1)]
    assert result.query == "What is a major triad?"
    assert result.status == "ready"
    assert len(result.items) == 1
    assert result.items[0].title == "Major triad"
    assert result.items[0].snippet == "A root, third, and f"
    assert result.items[0].content == "A root, third, and f"
    assert result.items[0].retrieved_at == "2026-09-29T10:00:00+00:00"
    assert budget.snapshot().web_search_calls == 1


@pytest.mark.anyio
async def test_web_search_adapter_accepts_empty_provider_results() -> None:
    adapter = WebSearchAdapter(_Provider(None), clock=lambda: "unused")
    budget = RunBudget()

    result = await adapter.search(AgentQuestion("unanswerable question"), budget)

    assert result.items == ()
    assert result.status == "no_results"
    assert budget.snapshot().completed_tool_calls == 1


@pytest.mark.anyio
async def test_web_search_adapter_rejects_malformed_urls_and_records_failure() -> None:
    provider = _Provider(
        [
            {
                "title": "Unsafe",
                "url": "javascript:alert(1)",
                "snippet": "Do not use this result.",
            }
        ]
    )
    adapter = WebSearchAdapter(provider)
    budget = RunBudget()

    with pytest.raises(ValueError, match=r"absolute HTTP\(S\) URL"):
        await adapter.search(AgentQuestion("unsafe result"), budget)

    snapshot = budget.snapshot()
    assert snapshot.web_search_calls == 1
    assert snapshot.failed_tool_calls == 1


@pytest.mark.anyio
async def test_web_search_adapter_requires_typed_question_and_budget() -> None:
    adapter = WebSearchAdapter(_Provider([]))

    with pytest.raises(ValueError, match="AgentQuestion"):
        await adapter.search("question", RunBudget())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RunBudget"):
        await adapter.search(AgentQuestion("question"), None)  # type: ignore[arg-type]


def test_web_search_item_requires_an_absolute_http_url() -> None:
    with pytest.raises(ValueError, match=r"absolute HTTP\(S\) URL"):
        WebSearchItem(
            title="Missing URL",
            url="",
            snippet="snippet",
            retrieved_at="2026-09-29T10:00:00+00:00",
        )
