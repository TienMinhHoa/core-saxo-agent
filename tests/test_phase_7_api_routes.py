from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from saxophone.app.factory import AppOverrides, create_app
from saxophone.app.settings import AppSettings
from saxophone.chat.models import ChatResult, ChatStatus
from saxophone.retrieval.models import EvidenceBundle


VALID_ENVIRONMENT = {
    "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
    "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
}


class FakeRemoteGpuGateway:
    async def health(self):
        from saxophone.platform.remote_gpu import RemoteGpuHealth

        return RemoteGpuHealth(status="ready", capabilities=("chat",))


class FakeModelClient:
    async def invoke(self, request):
        raise AssertionError("API route test must not invoke transport")


@dataclass
class FakeRetrieveEvidence:
    result: EvidenceBundle
    calls: list[tuple[str, int]]

    async def execute(self, query: str, *, filters=None, limit: int = 10):
        self.calls.append((query, limit))
        return self.result


@dataclass
class FakeAnswerQuestion:
    result: ChatResult
    calls: list[tuple[str, int]]

    async def execute(self, question: str, *, filters=None, limit: int = 10):
        self.calls.append((question, limit))
        return self.result


def settings() -> AppSettings:
    return AppSettings.from_environment(VALID_ENVIRONMENT)


def test_retrieval_route_returns_validated_evidence_projection() -> None:
    evidence = EvidenceBundle(
        query="harmony",
        retrieval_version="retrieval-v1",
        hits=(),
        selected_refs=(),
        source_texts={},
        insufficiency_reason="no matching evidence",
    )
    retriever = FakeRetrieveEvidence(evidence, [])
    app = create_app(
        settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
            retrieve_evidence=retriever,
        ),
    )

    response = TestClient(app).post(
        "/api/v1/retrieval/evidence",
        json={"query": "  harmony  ", "limit": 3},
    )

    assert response.status_code == 200
    assert response.json() == {
        "query": "harmony",
        "retrieval_version": "retrieval-v1",
        "selected_refs": [],
        "source_texts": {},
        "image_refs": [],
        "insufficiency_reason": "no matching evidence",
    }
    assert retriever.calls == [("harmony", 3)]


def test_chat_route_returns_safe_chat_result_without_private_reasoning() -> None:
    answerer = FakeAnswerQuestion(
        ChatResult(
            status=ChatStatus.INSUFFICIENT_EVIDENCE,
            answer=None,
            citations=(),
            evidence_bundle_ref=None,
            model_version=None,
            token_usage={},
            cost=0.0,
        ),
        [],
    )
    app = create_app(
        settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
            answer_question=answerer,
        ),
    )

    response = TestClient(app).post(
        "/api/v1/chat",
        json={"question": "What is harmony?", "limit": 2},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_evidence"
    assert "reasoning" not in response.text
    assert answerer.calls == [("What is harmony?", 2)]


def test_capability_routes_are_explicitly_unavailable_until_composed() -> None:
    app = create_app(
        settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
        ),
    )

    response = TestClient(app).post(
        "/api/v1/chat",
        json={"question": "hello"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "chat capability is not configured"}
