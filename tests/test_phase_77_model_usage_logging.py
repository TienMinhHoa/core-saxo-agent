from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from saxophone.platform.direct_model_client import DirectApiModelClient
from saxophone.platform.model_client import ModelRequest, ModelTask
from saxophone.platform.model_pricing import estimate_model_cost_usd
from saxophone.platform.observability import (
    DailyTextFileEventSink,
    InMemoryEventSink,
    StructuredEvent,
)


def test_peak_rate_cost_estimate_covers_deepseek_cache_and_output_tokens() -> None:
    cost = estimate_model_cost_usd(
        "deepseek-flash",
        input_tokens=20,
        output_tokens=10,
        cached_input_tokens=5,
    )

    assert cost == pytest.approx(0.00001653)


def test_embedding_cost_estimate_uses_input_tokens_only() -> None:
    cost = estimate_model_cost_usd(
        "text-embedding-3-small",
        input_tokens=4,
        output_tokens=0,
    )

    assert cost == pytest.approx(0.00000008)


def test_daily_text_sink_writes_safe_usage_to_current_date_file(tmp_path) -> None:
    sink = DailyTextFileEventSink(
        tmp_path,
        clock=lambda: datetime(2026, 9, 23, 14, 30, tzinfo=timezone.utc),
    )
    sink.emit(
        StructuredEvent(
            name="model.request.completed",
            correlation_id="chunk-1",
            task="chunk_tagging",
            model="deepseek-flash",
            attempt=1,
            duration_ms=125.5,
            input_count=1,
            output_count=1,
            result="success",
            input_tokens=120,
            output_tokens=30,
            cost_usd=0.000072,
            pricing_basis="deepseek-peak-2026-09-23",
        )
    )

    content = (tmp_path / "2026-09-23.log").read_text(encoding="utf-8")
    assert "event=model.request.completed" in content
    assert "task=chunk_tagging" in content
    assert "model=deepseek-flash" in content
    assert "input_tokens=120" in content
    assert "output_tokens=30" in content
    assert "total_tokens=150" in content
    assert "estimated_cost_usd=0.000072000000" in content
    assert "pricing_basis=deepseek-peak-2026-09-23" in content
    assert "prompt" not in content
    assert "api_key" not in content


@pytest.mark.anyio
async def test_direct_client_emits_exact_provider_usage_and_estimated_cost() -> None:
    sink = InMemoryEventSink()

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"labels": []}'}}],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "prompt_cache_hit_tokens": 5,
                    "prompt_cache_miss_tokens": 15,
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = _client(http_client, event_sink=sink)
        await client.invoke(
            ModelRequest(
                model="saxophone-direct-v1",
                task=ModelTask.CHUNK_TAGGING,
                input={
                    "system_prompt": "Return JSON.",
                    "user_prompt": "Tag this chunk.",
                    "response_format": "json_object",
                },
                metadata={"source_version": "source-v1"},
                response_schema="chunk-tags-v1",
                idempotency_key="chunk-1",
            )
        )

    event = sink.events[0]
    assert event.name == "model.request.completed"
    assert event.model == "deepseek-flash"
    assert event.input_tokens == 20
    assert event.output_tokens == 10
    assert event.cost_usd == pytest.approx(0.00001653)
    assert event.pricing_basis == "deepseek-peak-2026-09-23"


@pytest.mark.anyio
async def test_direct_client_emits_embedding_input_tokens_and_cost() -> None:
    sink = InMemoryEventSink()

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [0.1, 0.2]}],
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = _client(http_client, event_sink=sink)
        await client.invoke(
            ModelRequest(
                model="saxophone-direct-v1",
                task=ModelTask.EMBED,
                input={"texts": [{"chunk_id": "chunk-1", "text": "Major triad"}]},
                metadata={"source_version": "source-v1"},
                response_schema="embedding-v1",
                idempotency_key="embed-1",
            )
        )

    event = sink.events[0]
    assert event.model == "text-embedding-3-small"
    assert event.input_tokens == 4
    assert event.output_tokens == 0
    assert event.cost_usd == pytest.approx(0.00000008)
    assert event.pricing_basis == "openai-standard-2026-09-23"


@pytest.mark.anyio
async def test_direct_client_logs_failure_without_inventing_token_usage() -> None:
    sink = InMemoryEventSink()

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = _client(http_client, event_sink=sink)
        with pytest.raises(httpx.HTTPStatusError):
            await client.invoke(
                ModelRequest(
                    model="saxophone-direct-v1",
                    task=ModelTask.CHUNK_TAGGING,
                    input={
                        "system_prompt": "Return JSON.",
                        "user_prompt": "Tag this chunk.",
                        "response_format": "json_object",
                    },
                    metadata={"source_version": "source-v1"},
                    response_schema="chunk-tags-v1",
                    idempotency_key="chunk-1",
                )
            )

    event = sink.events[0]
    assert event.name == "model.request.failed"
    assert event.result == "failure"
    assert event.input_tokens is None
    assert event.output_tokens is None
    assert event.cost_usd is None


@pytest.mark.anyio
async def test_direct_client_keeps_billable_usage_when_provider_output_is_invalid() -> None:
    sink = InMemoryEventSink()

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "not-json"}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = _client(http_client, event_sink=sink)
        with pytest.raises(ValueError, match="valid JSON"):
            await client.invoke(
                ModelRequest(
                    model="saxophone-direct-v1",
                    task=ModelTask.CHUNK_TAGGING,
                    input={
                        "system_prompt": "Return JSON.",
                        "user_prompt": "Tag this chunk.",
                        "response_format": "json_object",
                    },
                    metadata={"source_version": "source-v1"},
                    response_schema="chunk-tags-v1",
                    idempotency_key="chunk-1",
                )
            )

    event = sink.events[0]
    assert event.name == "model.request.failed"
    assert event.input_tokens == 20
    assert event.output_tokens == 10
    assert event.cost_usd == pytest.approx(0.000018)


def _client(
    http_client: httpx.AsyncClient,
    *,
    event_sink: InMemoryEventSink,
) -> DirectApiModelClient:
    return DirectApiModelClient(
        http_client=http_client,
        deepseek_api_base_url="https://api.deepseek.com",
        deepseek_api_key="deepseek-secret",
        deepseek_model="deepseek-flash",
        deepseek_reasoning_effort="max",
        deepseek_max_tokens=65536,
        openai_api_base_url="https://api.openai.com/v1",
        openai_api_key="openai-secret",
        openai_embedding_model="text-embedding-3-small",
        embedding_dimension=2,
        event_sink=event_sink,
        max_attempts=1,
    )
