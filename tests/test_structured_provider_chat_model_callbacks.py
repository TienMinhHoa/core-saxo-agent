from __future__ import annotations

import pytest

from saxophone.agent.logging import AgentLoggingCallbackHandler
from saxophone.platform.langchain_model import StructuredProviderChatModel


class _Provider:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail = fail

    async def generate_structured(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("provider failed")
        return {"answer": "ok"}


class _Schema:
    pass


@pytest.mark.anyio
async def test_logging_callback_does_not_block_structured_model_success() -> None:
    provider = _Provider()
    model = StructuredProviderChatModel(provider=provider, model_name="answer-model")
    runnable = model.with_structured_output(_Schema)

    result = await runnable.ainvoke(
        {"system": "system", "user": "user"},
        config={"callbacks": [AgentLoggingCallbackHandler(run_id="run-success")]},
    )

    assert result == {"answer": "ok"}
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_logging_callback_does_not_mask_structured_model_failure() -> None:
    provider = _Provider(fail=True)
    model = StructuredProviderChatModel(provider=provider, model_name="answer-model")
    runnable = model.with_structured_output(_Schema)

    with pytest.raises(RuntimeError, match="provider failed"):
        await runnable.ainvoke(
            {"system": "system", "user": "user"},
            config={"callbacks": [AgentLoggingCallbackHandler(run_id="run-failure")]},
        )

    assert len(provider.calls) == 1
