from __future__ import annotations

import importlib
import json

import httpx
import pytest

from saxophone.agent.contracts import AgentQuestion, RunBudget
from saxophone.agent.web_search import WebSearchAdapter
from saxophone.app.settings import AppSettings, SettingsValidationError


def _client(http_client: httpx.AsyncClient, **kwargs):
    module = importlib.import_module("saxophone.platform.web_search_client")
    return module.TavilySearchClient(
        http_client=http_client, api_key="tvly-test-secret", **kwargs
    )


def _environment(**overrides: str) -> dict[str, str]:
    return {
        "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
        "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
        **overrides,
    }


def test_tavily_is_optional_and_credential_is_not_in_settings_repr() -> None:
    defaults = AppSettings.from_environment(_environment())
    configured = AppSettings.from_environment(
        _environment(TAVILY_API_KEY="tvly-test-secret")
    )

    assert defaults.tavily_api_key is None
    assert configured.tavily_api_key == "tvly-test-secret"
    assert "tvly-test-secret" not in repr(configured)


@pytest.mark.parametrize("key", [" ", "secret\nforged", "secret\x00"])
def test_tavily_settings_reject_unsafe_credentials_without_echoing_them(key) -> None:
    with pytest.raises(SettingsValidationError) as captured:
        AppSettings.from_environment(_environment(TAVILY_API_KEY=key))

    assert "TAVILY_API_KEY" in str(captured.value)
    if key.strip():
        assert key not in str(captured.value)


@pytest.mark.anyio
async def test_tavily_search_uses_original_query_and_normalizes_bounded_results() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Major triad",
                        "url": "https://example.test/triad",
                        "content": "A root, third, and fifth.",
                        "raw_content": "A root, third, and fifth. More details.",
                    },
                    {"title": "Extra", "url": "https://example.test/extra", "content": "Extra"},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        provider = _client(http_client)
        budget = RunBudget(max_hits_per_tool=1)
        result = await WebSearchAdapter(provider, max_content_chars=24).search(
            AgentQuestion("What is 145 formula?"), budget
        )
        assert not http_client.is_closed

    payload = json.loads(requests[0].content)
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "https://api.tavily.com/search"
    assert payload["query"] == "What is 145 formula?"
    assert payload["max_results"] == 1
    assert payload.get("include_answer", False) is False
    assert "tvly-test-secret" in (
        requests[0].headers.get("authorization", "") + str(payload.get("api_key", ""))
    )
    assert len(result.items) == 1
    assert result.items[0].title == "Major triad"
    assert result.items[0].url == "https://example.test/triad"
    assert len(result.items[0].content) <= 24
    assert result.items[0].retrieved_at
    assert budget.snapshot().completed_tool_calls == 1


@pytest.mark.anyio
async def test_tavily_empty_results_remain_insufficient_evidence() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"results": []}))
    ) as http_client:
        result = await WebSearchAdapter(_client(http_client)).search(
            AgentQuestion("Unknown topic"), RunBudget()
        )

    assert result.status == "no_results"
    assert result.items == ()


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 429, 500])
async def test_tavily_http_errors_hide_secrets_and_are_not_retried_without_budget(status) -> None:
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, text="tvly-test-secret raw provider details")

    budget = RunBudget()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(Exception) as captured:
            await WebSearchAdapter(_client(http_client)).search(AgentQuestion("Triads"), budget)

    assert len(calls) == 1
    assert "tvly-test-secret" not in str(captured.value)
    assert "raw provider details" not in str(captured.value)
    assert budget.snapshot().failed_tool_calls == 1


@pytest.mark.anyio
@pytest.mark.parametrize("payload", [{}, {"results": "invalid"}, {"results": [{}]}])
async def test_tavily_rejects_malformed_provider_response(payload) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as http_client:
        with pytest.raises((ValueError, RuntimeError)):
            await WebSearchAdapter(_client(http_client)).search(AgentQuestion("Triads"), RunBudget())


@pytest.mark.anyio
async def test_tavily_timeout_closes_budget_reservation() -> None:
    def respond(request):
        raise httpx.ReadTimeout("tvly-test-secret", request=request)

    budget = RunBudget()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        with pytest.raises(Exception) as captured:
            await WebSearchAdapter(_client(http_client)).search(AgentQuestion("Triads"), budget)

    assert "tvly-test-secret" not in str(captured.value)
    assert budget.snapshot().failed_tool_calls == 1


@pytest.mark.anyio
@pytest.mark.parametrize("query,limit", [(" ", 1), ("Triads", 0), ("Triads", True)])
async def test_tavily_rejects_invalid_request_before_http(query, limit) -> None:
    calls = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: calls.append(request))
    ) as http_client:
        with pytest.raises(ValueError):
            await _client(http_client).search(query, limit=limit)

    assert calls == []
