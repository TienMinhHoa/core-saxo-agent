from __future__ import annotations

import pytest

from saxophone.chat.models import GeneratedAnswer
from saxophone.chat.remote_answer import RemoteAnswerGenerator
from saxophone.platform.model_client import (
    ModelRequest,
    ModelResponse,
    ModelTask,
    ModelValidationError,
)
from saxophone.retrieval.models import ChunkHit, EvidenceBundle


class _ModelClient:
    def __init__(self, response: ModelResponse) -> None:
        self.response = response
        self.requests: list[ModelRequest] = []

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return self.response


def _evidence() -> EvidenceBundle:
    hit = ChunkHit(
        "book-1",
        "chunk-1",
        1,
        "retrieval-v1",
        {"document": "Long tones build stable intonation."},
        semantic_score=0.9,
    )
    return EvidenceBundle(
        "How should I practice?",
        "retrieval-v1",
        (hit,),
        ("chunk-1",),
        {"chunk-1": "Long tones build stable intonation."},
    )


@pytest.mark.anyio
async def test_remote_answer_generator_maps_typed_model_response() -> None:
    client = _ModelClient(
        ModelResponse(
            ModelTask.ANSWER_GENERATE,
            "answer-model-v1",
            "answer-v1",
            {
                "answer": "Start with long tones.",
                "token_usage": {"prompt": 12, "completion": 6, "total": 18},
                "cost": 0.001,
            },
            "evidence://retrieval-v1/abc",
        )
    )

    generated = await RemoteAnswerGenerator(
        client, model="answer-model-v1", response_schema="answer-v1"
    ).generate("How should I practice?", _evidence())

    assert generated == GeneratedAnswer(
        "Start with long tones.",
        "answer-model-v1",
        {"prompt": 12, "completion": 6, "total": 18},
        0.001,
    )
    assert client.requests[0].task is ModelTask.ANSWER_GENERATE
    assert client.requests[0].input["question"] == "How should I practice?"
    assert client.requests[0].input["source_texts"] == {
        "chunk-1": "Long tones build stable intonation."
    }


@pytest.mark.anyio
async def test_remote_answer_generator_rejects_wrong_response_task() -> None:
    client = _ModelClient(
        ModelResponse(
            ModelTask.EMBED,
            "answer-model-v1",
            "answer-v1",
            {"answer": "wrong"},
            "source-v1",
        )
    )

    with pytest.raises(ModelValidationError, match="answer_generate"):
        await RemoteAnswerGenerator(
            client, model="answer-model-v1", response_schema="answer-v1"
        ).generate("How?", _evidence())


@pytest.mark.anyio
async def test_remote_answer_generator_rejects_malformed_model_output() -> None:
    client = _ModelClient(
        ModelResponse(
            ModelTask.ANSWER_GENERATE,
            "answer-model-v1",
            "answer-v1",
            {"answer": "ok", "token_usage": {"total": "18"}},
            "source-v1",
        )
    )

    with pytest.raises(ModelValidationError, match="token_usage"):
        await RemoteAnswerGenerator(
            client, model="answer-model-v1", response_schema="answer-v1"
        ).generate("How?", _evidence())
