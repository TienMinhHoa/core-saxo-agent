from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from saxophone.app.factory import AppOverrides, create_app
from saxophone.app.settings import AppSettings
from saxophone.chat.models import ChatResult, ChatStatus
from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.documents.ports import ArtifactRepository
from saxophone.extraction.models import PdfExtractionResult
from saxophone.retrieval.models import EvidenceBundle
from saxophone.workflows.process_document import ProcessDocument


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


@dataclass
class FakePdfExtractor:
    result: PdfExtractionResult
    calls: list[tuple[str, str]]

    async def extract(self, request):
        self.calls.append((request.document_ref, request.correlation_id))
        return self.result


@dataclass
class FakeArtifacts(ArtifactRepository):
    payload: bytes
    puts: list[tuple[ArtifactRef, bytes]] | None = None

    async def put(self, artifact: ArtifactRef, payload: bytes) -> None:
        self.payload = payload
        if self.puts is not None:
            self.puts.append((artifact, payload))

    async def get(self, artifact: ArtifactRef) -> bytes:
        return self.payload


def settings() -> AppSettings:
    return AppSettings.from_environment(VALID_ENVIRONMENT)


def _artifact(artifact_id: str, kind: ArtifactKind) -> ArtifactRef:
    import hashlib

    return ArtifactRef(
        artifact_id=artifact_id,
        version="v1",
        kind=kind,
        media_type="application/octet-stream",
        sha256=hashlib.sha256(artifact_id.encode()).hexdigest(),
        size_bytes=len(artifact_id),
    )


def test_document_process_route_delegates_to_typed_extractor() -> None:
    result = PdfExtractionResult(
        document_ref="doc-1",
        source_version="source-v1",
        markdown=_artifact("markdown", ArtifactKind.MARKDOWN),
        layout=_artifact("layout", ArtifactKind.LAYOUT),
        manifest=_artifact("manifest", ArtifactKind.EXTRACTION_MANIFEST),
        coordinates=(),
        model_profile="extractor-v1",
    )
    extractor = FakePdfExtractor(result, [])
    workflow = ProcessDocument(FakeArtifacts(b"source"), extractor)
    app = create_app(
        settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
            pdf_extractor=extractor,
            process_document=workflow,
        ),
    )

    response = TestClient(app).post(
        "/api/v1/documents/doc-1/process",
        json={
            "source": {
                "artifact_id": "source",
                "version": "v1",
                "kind": "source_pdf",
                "media_type": "application/pdf",
                "sha256": "41cf6794ba4200b839c53531555f0f3998df4cbb01a4d5cb0b94e3ca5e23947d",
                "size_bytes": 6,
            },
            "source_version": "source-v1",
            "correlation_id": "corr-1",
            "model_profile": "extractor-v1",
        },
    )

    assert response.status_code == 200
    assert response.json()["document_ref"] == "doc-1"
    assert response.json()["markdown"]["artifact_id"] == "markdown"
    assert extractor.calls == [("doc-1", "corr-1")]


def test_document_process_route_rejects_source_that_workflow_cannot_verify() -> None:
    result = PdfExtractionResult(
        document_ref="doc-1",
        source_version="source-v1",
        markdown=_artifact("markdown", ArtifactKind.MARKDOWN),
        layout=_artifact("layout", ArtifactKind.LAYOUT),
        manifest=_artifact("manifest", ArtifactKind.EXTRACTION_MANIFEST),
        coordinates=(),
        model_profile="extractor-v1",
    )
    extractor = FakePdfExtractor(result, [])
    workflow = ProcessDocument(FakeArtifacts(b"wrong"), extractor)
    app = create_app(
        settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
            pdf_extractor=extractor,
            process_document=workflow,
        ),
    )

    response = TestClient(app).post(
        "/api/v1/documents/doc-1/process",
        json={
            "source": {
                "artifact_id": "source",
                "version": "v1",
                "kind": "source_pdf",
                "media_type": "application/pdf",
                "sha256": "41cf6794ba4200b839c53531555f0f3998df4cbb01a4d5cb0b94e3ca5e23947d",
                "size_bytes": 6,
            },
            "source_version": "source-v1",
            "correlation_id": "corr-1",
            "model_profile": "extractor-v1",
        },
    )

    assert response.status_code == 422
    assert extractor.calls == []


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


def test_source_upload_persists_pdf_and_returns_typed_artifact_reference() -> None:
    artifacts = FakeArtifacts(b"", puts=[])
    app = create_app(
        settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
            artifact_repository=artifacts,
        ),
    )

    response = TestClient(app).post(
        "/api/v1/documents/doc-1/source",
        files={"file": ("source.pdf", b"%PDF-1.7", "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["artifact_id"] == "doc-1/source"
    assert body["version"] == "v1"
    assert body["kind"] == "source_pdf"
    assert body["media_type"] == "application/pdf"
    assert body["size_bytes"] == 8
    assert len(body["sha256"]) == 64
    assert artifacts.puts is not None
    assert artifacts.puts[0][1] == b"%PDF-1.7"


def test_source_upload_rejects_non_pdf_without_persisting() -> None:
    artifacts = FakeArtifacts(b"", puts=[])
    app = create_app(
        settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
            artifact_repository=artifacts,
        ),
    )

    response = TestClient(app).post(
        "/api/v1/documents/doc-1/source",
        files={"file": ("source.txt", b"not pdf", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json() == {"detail": "uploaded file must have media type application/pdf"}
    assert artifacts.puts == []
