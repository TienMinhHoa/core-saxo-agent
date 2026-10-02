from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient
from langchain_core.callbacks import BaseCallbackHandler

from saxophone.agent.evidence import EvidenceLedgerBuilder
from saxophone.agent.synthesis import EvidenceSynthesisService
from saxophone.app.factory import AppOverrides, create_app
from saxophone.app.settings import AppSettings


class _Gateway:
    async def health(self):
        raise AssertionError("test must not call remote health")


class _ModelClient:
    async def invoke(self, request):
        from saxophone.platform.model_client import ModelResponse, ModelTask
        output = (
            {"action": "finish", "tool_name": None, "arguments": {}}
            if request.task is ModelTask.ORCHESTRATOR_DECISION
            else {"queries": ["music theory unknown topic", "music theory definitions examples"]}
            if request.task is ModelTask.DOCUMENT_SEARCH_QUERY_PLAN
            else {"answer": "No grounded context was found.", "evidence_sufficient": False, "used_evidence_ids": [], "citations": []}
        )
        return ModelResponse(request.task, request.model, request.response_schema, output, "test-v1")


class _Embeddings:
    async def embed_texts(self, texts):
        return [[0.1, 0.2] for text in texts]


class _VectorIndex:
    async def list_chunk_ids(self, *, document_ref):
        return ()

    async def upsert_chunks(self, records):
        pass

    async def delete_chunks(self, chunk_ids):
        pass

    async def upsert_concepts(self, records):
        pass

    async def delete_concepts(self, record_ids):
        pass

    async def search(self, query_vector, *, filters=None, limit=10):
        return []


def _settings(tmp_path, provider="gateway", **extra):
    return AppSettings.from_environment({
        "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
        "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
        "SAXO_DATA_ROOT": str(tmp_path),
        "SAXO_CHUNK_TAGGING_ENABLED": "true",
        "SAXO_MODEL_PROVIDER": provider,
        **({"DEEPSEEK_API_KEY": "test-deepseek", "OPENAI_API_KEY": "test-openai"}
           if provider == "direct" else {}),
        **extra,
    })


@pytest.mark.parametrize("provider", ["gateway", "direct"])
def test_topic_capability_automatically_composes_compiled_main_agent(tmp_path, provider) -> None:
    app = create_app(
        _settings(tmp_path, provider), overrides=AppOverrides(
            remote_gpu_gateway=_Gateway(), model_client=_ModelClient(),
            vector_index=_VectorIndex(), embedding_provider=_Embeddings(),
        ),
    )
    with TestClient(app) as client:
        runner = app.state.container.agent_runner
        assert runner is not None, "production must not require injecting a prebuilt agent"
        graph = runner.graph
        first = client.post("/agent/chat/stream", json={"question": "Unknown topic"})
        second = client.post("/agent/chat/stream", json={"question": "Another topic"})
        json_response = client.post("/agent/chat/messages", json={"question": "Unknown topic"})

        assert first.status_code == second.status_code == 200
        assert runner.graph is graph
        assert "answered" in first.text
        assert "run_result" in first.text
        assert app.state.container.agent_chat is not None
        assert json_response.status_code == 200
        assert json_response.json()["status"] == "answered"


def test_missing_vector_capability_keeps_stream_disabled(tmp_path) -> None:
    app = create_app(_settings(tmp_path), overrides=AppOverrides(
        remote_gpu_gateway=_Gateway(), model_client=_ModelClient(), disable_vector_index=True,
    ))
    with TestClient(app) as client:
        assert app.state.container.agent_runner is None
        assert client.post("/agent/chat/stream", json={"question": "Triads?"}).status_code == 503


def test_prebuilt_runner_override_takes_precedence_over_automatic_composition(tmp_path) -> None:
    class Runner:
        async def run(self, *args, **kwargs):
            raise AssertionError("composition must not run the agent")

    runner = Runner()
    app = create_app(_settings(tmp_path), overrides=AppOverrides(
        remote_gpu_gateway=_Gateway(), model_client=_ModelClient(),
        vector_index=_VectorIndex(), embedding_provider=_Embeddings(), agent_runner=runner,
    ))
    with TestClient(app):
        assert app.state.container.agent_runner is runner


class _Provider:
    def __init__(self, foreign_evidence=False):
        self.calls = []
        self.foreign_evidence = foreign_evidence

    async def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        evidence_id = "foreign" if self.foreign_evidence else "document:known"
        return kwargs["response_model"].model_validate({
            "answer": "A triad has three notes [1].",
            "evidence_sufficient": True, "used_evidence_ids": [evidence_id],
            "citations": [{"evidence_id": evidence_id, "label": "[1]"}],
        })


class _Callbacks(BaseCallbackHandler):
    def __init__(self):
        self.model_starts = []
        self.model_ends = []

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.model_starts.append(kwargs)

    def on_llm_start(self, serialized, prompts, **kwargs):
        self.model_starts.append(kwargs)

    def on_llm_end(self, response, **kwargs):
        self.model_ends.append(kwargs)


@pytest.mark.anyio
async def test_production_structured_provider_adapter_runs_synthesis_with_model_callbacks() -> None:
    module = importlib.import_module("saxophone.platform.langchain_model")
    provider = _Provider()
    model = module.StructuredProviderChatModel(provider=provider, model_name="test-chat")
    callback = _Callbacks()
    builder = EvidenceLedgerBuilder(run_id="run-provider", question="Triads?", selected_strategy="paragraph_direct")
    builder.add_document(
        evidence_id="document:known", source_ref="music.md", chunk_id="chunk-1",
        paragraph_ref="paragraph-1", text="A triad has three notes.", page=1,
    )

    result = await EvidenceSynthesisService(model).synthesize(
        builder.build(), config={"callbacks": [callback]}
    )

    assert result.used_evidence_ids == ("document:known",)
    assert provider.calls[0]["task_type"] == "answer_generation"
    assert provider.calls[0]["system_prompt"] == provider.calls[0]["system_prompt"].strip()
    assert "A triad has three notes." in provider.calls[0]["user_prompt"]
    assert len(callback.model_starts) == len(callback.model_ends) == 1


@pytest.mark.anyio
async def test_production_adapter_cannot_bypass_ledger_validation() -> None:
    module = importlib.import_module("saxophone.platform.langchain_model")
    model = module.StructuredProviderChatModel(provider=_Provider(foreign_evidence=True), model_name="test-chat")
    builder = EvidenceLedgerBuilder(run_id="run-provider", question="Triads?", selected_strategy="paragraph_direct")
    builder.add_document(
        source_ref="music.md", chunk_id="chunk-1", paragraph_ref="paragraph-1",
        text="A triad has three notes.", page=1,
    )

    with pytest.raises(ValueError):
        await EvidenceSynthesisService(model).synthesize(builder.build())
