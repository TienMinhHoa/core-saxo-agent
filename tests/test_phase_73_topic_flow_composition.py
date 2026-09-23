from __future__ import annotations

from pathlib import Path

from saxophone.app.factory import AppOverrides, create_app
from saxophone.app.settings import AppSettings
from saxophone.chat.service import GroundedAnswerService
from saxophone.retrieval.question_retrieval import QuestionRetrievalService
from saxophone.services.extract_topic import ExtractTopicService


class _RemoteGpu:
    async def health(self):
        raise AssertionError("composition test must not call providers")


class _ModelClient:
    async def invoke(self, request):
        raise AssertionError("composition test must not call providers")


class _SearchableVectorIndex:
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


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings.from_environment(
        {
            "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
            "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
            "SAXO_DATA_ROOT": str(tmp_path),
            "SAXO_CHUNK_TAGGING_ENABLED": "true",
        }
    )


def test_topic_services_are_composed_without_adding_an_http_endpoint(tmp_path: Path) -> None:
    app = create_app(
        _settings(tmp_path),
        overrides=AppOverrides(
            remote_gpu_gateway=_RemoteGpu(),
            model_client=_ModelClient(),
            vector_index=_SearchableVectorIndex(),
        ),
    )
    container = app.state.container

    assert isinstance(container.question_retrieval, QuestionRetrievalService)
    assert isinstance(container.grounded_answer, GroundedAnswerService)
    assert isinstance(container.extract_topic, ExtractTopicService)
    assert not any(
        getattr(route, "path", "").startswith("/api/v1/topic")
        for route in app.routes
    )
