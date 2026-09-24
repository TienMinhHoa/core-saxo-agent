from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from saxophone.app.factory import AppOverrides, create_app
from saxophone.app.settings import AppSettings, SettingsValidationError
from saxophone.chat.service import (
    AnswerSource,
    GroundedAnswerResponse,
    GroundedAnswerService,
    GroundedAnswerStatus,
)
from saxophone.interfaces.api import build_agent_chat_router
from saxophone.platform.direct_model_client import DirectApiModelClient
from saxophone.retrieval.question_retrieval import QuestionRequest
from saxophone.tagging.structured_provider import RemoteStructuredLlmProvider


@dataclass
class _AgentChat:
    response: GroundedAnswerResponse
    calls: list[QuestionRequest]

    async def answer(self, request: QuestionRequest) -> GroundedAnswerResponse:
        self.calls.append(request)
        return self.response


def _router_app(agent_chat: object | None) -> FastAPI:
    app = FastAPI()
    app.include_router(build_agent_chat_router(agent_chat=agent_chat))
    return app


def test_agent_chat_page_serves_separate_html_css_and_javascript_assets() -> None:
    client = TestClient(_router_app(None))

    page = client.get("/agent/chat")
    stylesheet = client.get("/agent/chat/assets/chat.css")
    script = client.get("/agent/chat/assets/chat.js")

    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert 'href="/agent/chat/assets/chat.css"' in page.text
    assert 'src="/agent/chat/assets/chat.js"' in page.text
    assert 'id="chat-form"' in page.text
    assert "Hỏi tài liệu" in page.text
    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert "--ink:" in stylesheet.text
    assert script.status_code == 200
    assert "application/javascript" in script.headers["content-type"]
    assert 'fetch("/agent/chat/messages"' in script.text
    assert "document.createElement(\"details\")" in script.text
    assert '"Bạn"' in script.text
    assert "nguồn đã sử dụng" in script.text
    assert "source.citation" in script.text


def test_agent_chat_message_endpoint_runs_grounded_question_flow() -> None:
    service = _AgentChat(
        GroundedAnswerResponse(
            GroundedAnswerStatus.ANSWERED,
            "Rhythm organizes the musical pulse.",
            (
                AnswerSource(
                    paragraph_ref="paragraph-1",
                    chunk_id="chunk-1",
                    source="music-theory.md",
                    page_start=12,
                    page_end=13,
                    image_refs=("figure-12-1",),
                ),
            ),
            "deepseek-pro",
        ),
        [],
    )

    response = TestClient(_router_app(service)).post(
        "/agent/chat/messages",
        json={
            "question": "  What is rhythm?  ",
            "filters": {"document_ref": "music-theory-pilot"},
            "chunk_limit": 7,
            "max_paragraphs": 12,
            "max_tokens": 2400,
        },
    )

    assert response.status_code == 200
    assert service.calls == [
        QuestionRequest(
            "What is rhythm?",
            filters={"document_ref": "music-theory-pilot"},
            chunk_limit=7,
            max_paragraphs=12,
            max_tokens=2400,
        )
    ]
    assert response.json() == {
        "status": "answered",
        "answer": "Rhythm organizes the musical pulse.",
        "sources": [
            {
                "citation": "[1]",
                "paragraph_ref": "paragraph-1",
                "chunk_id": "chunk-1",
                "source": "music-theory.md",
                "page_start": 12,
                "page_end": 13,
                "image_refs": ["figure-12-1"],
            }
        ],
        "model_version": "deepseek-pro",
    }


def test_agent_chat_message_endpoint_reports_unconfigured_capability() -> None:
    response = TestClient(_router_app(None)).post(
        "/agent/chat/messages",
        json={"question": "What is rhythm?"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "agent chat capability is not configured"}


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "   "},
        {"question": "What is rhythm?", "chunk_limit": 0},
        {"question": "What is rhythm?", "max_paragraphs": 0},
        {"question": "What is rhythm?", "max_tokens": 0},
    ],
)
def test_agent_chat_message_endpoint_rejects_invalid_requests(
    payload: dict[str, object],
) -> None:
    response = TestClient(_router_app(None)).post("/agent/chat/messages", json=payload)

    assert response.status_code == 422


def test_agent_chat_model_has_a_dedicated_environment_setting() -> None:
    base = {
        "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
        "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
    }

    defaults = AppSettings.from_environment(base)
    configured = AppSettings.from_environment(
        {**base, "SAXO_AGENT_CHAT_MODEL": "deepseek-pro-v2"}
    )

    assert defaults.agent_chat_model == "deepseek-pro"
    assert configured.agent_chat_model == "deepseek-pro-v2"


@pytest.mark.parametrize("value", ["", "   ", "deepseek-pro\nforged"])
def test_agent_chat_model_rejects_invalid_values(value: str) -> None:
    with pytest.raises(SettingsValidationError, match="SAXO_AGENT_CHAT_MODEL"):
        AppSettings.from_environment(
            {
                "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
                "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
                "SAXO_AGENT_CHAT_MODEL": value,
            }
        )


class _RemoteGpu:
    async def health(self):
        raise AssertionError("composition test must not call provider health")


class _ModelClient:
    async def invoke(self, request):
        raise AssertionError("composition test must not call the model")


class _EmbeddingProvider:
    async def embed(self, chunks, *, source_version: str):
        raise AssertionError("composition test must not embed")

    async def embed_texts(self, texts):
        raise AssertionError("composition test must not embed query text")


class _VectorIndex:
    async def list_chunk_ids(self, *, document_ref: str):
        return ()

    async def upsert_chunks(self, records):
        return None

    async def delete_chunks(self, chunk_ids):
        return None

    async def upsert_concepts(self, records):
        return None

    async def delete_concepts(self, record_ids):
        return None

    async def search(self, query_vector, *, filters=None, limit: int = 10):
        return []


def test_composition_exposes_chat_ui_and_uses_dedicated_agent_model(tmp_path: Path) -> None:
    settings = AppSettings.from_environment(
        {
            "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
            "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
            "SAXO_DATA_ROOT": str(tmp_path),
            "SAXO_CHUNK_TAGGING_ENABLED": "true",
            "SAXO_AGENT_CHAT_MODEL": "deepseek-pro-test",
        }
    )
    app = create_app(
        settings,
        overrides=AppOverrides(
            remote_gpu_gateway=_RemoteGpu(),
            model_client=_ModelClient(),
            embedding_provider=_EmbeddingProvider(),
            vector_index=_VectorIndex(),
        ),
    )
    container = app.state.container

    assert isinstance(container.agent_chat, GroundedAnswerService)
    assert isinstance(container.agent_structured_llm_provider, RemoteStructuredLlmProvider)
    assert container.agent_chat._model_version == "deepseek-pro-test"
    assert container.agent_structured_llm_provider._model == "deepseek-pro-test"
    client = TestClient(app)
    assert client.get("/agent/chat").status_code == 200


def test_direct_provider_uses_separate_deepseek_model_for_agent_answers(
    tmp_path: Path,
) -> None:
    settings = AppSettings.from_environment(
        {
            "SAXO_MODEL_PROVIDER": "direct",
            "DEEPSEEK_API_KEY": "deepseek-secret",
            "OPENAI_API_KEY": "openai-secret",
            "SAXO_DATA_ROOT": str(tmp_path),
            "SAXO_CHUNK_TAGGING_ENABLED": "true",
            "SAXO_AGENT_CHAT_MODEL": "deepseek-pro-test",
        }
    )

    app = create_app(
        settings,
        overrides=AppOverrides(
            remote_gpu_gateway=_RemoteGpu(),
            embedding_provider=_EmbeddingProvider(),
            vector_index=_VectorIndex(),
        ),
    )
    container = app.state.container
    agent_provider = container.agent_structured_llm_provider

    assert isinstance(container.model_client, DirectApiModelClient)
    assert container.model_client._deepseek_model == "deepseek-flash"
    assert isinstance(agent_provider, RemoteStructuredLlmProvider)
    assert isinstance(agent_provider._client, DirectApiModelClient)
    assert agent_provider._client is not container.model_client
    assert agent_provider._client._deepseek_model == "deepseek-pro-test"
