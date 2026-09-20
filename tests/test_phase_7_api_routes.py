from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from fastapi.testclient import TestClient

from saxophone.app.factory import AppOverrides, create_app
from saxophone.app.settings import AppSettings
from saxophone.chat.models import ChatResult, ChatStatus
from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.documents.ports import ArtifactRepository
from saxophone.extraction.models import PdfExtractionResult
from saxophone.ingestion.adapters import InMemoryEmbeddingReuseStore
from saxophone.ingestion.models import EmbeddingRecord
from saxophone.ingestion.use_cases import IngestDocument, IndexDocument
from saxophone.retrieval.models import EvidenceBundle
from saxophone.tagging.models import (
    TagConflictResolution,
    TagGenerationResult,
    TagResolution,
    TaggedParagraph,
)
from saxophone.tagging.persistence import JsonTagCatalogRepository, JsonTaggedParagraphRepository
from saxophone.workflows.ingest_extracted_document import IngestExtractedDocument
from saxophone.workflows.process_document import ProcessAndPersistDocument, ProcessDocument


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


class FakeExtractionPayloads:
    def __init__(self, markdown: bytes = b"markdown") -> None:
        self.markdown = markdown

    async def fetch(self, result: PdfExtractionResult) -> dict[str, bytes]:
        return {"markdown": self.markdown, "layout": b"layout", "manifest": b"manifest"}


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


@dataclass
class MultiArtifactRepository(ArtifactRepository):
    payloads: dict[str, bytes]
    puts: list[tuple[ArtifactRef, bytes]]

    async def put(self, artifact: ArtifactRef, payload: bytes) -> None:
        self.payloads[artifact.artifact_id] = payload
        self.puts.append((artifact, payload))

    async def get(self, artifact: ArtifactRef) -> bytes:
        return self.payloads[artifact.artifact_id]


class FakeVectorIndex:
    def __init__(self) -> None:
        self.records = ()

    async def upsert_chunks(self, records):
        self.records = tuple(records)


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.calls = []

    async def embed(self, chunks, *, source_version):
        self.calls.append((tuple(chunks), source_version))
        return tuple(
            EmbeddingRecord(
                chunk_id=chunk_id,
                source_version=source_version,
                model_profile="embed-v1",
                vector=(0.9, 0.8),
            )
            for chunk_id, _ in chunks
        )


class FakeTagAndPersist:
    async def execute(self, paragraph, *, tagging_profile, resolution_profile):
        return TaggedParagraph(
            paragraph_id=paragraph.paragraph_id,
            text=paragraph.text,
            generated_tags=("music",),
            tags=("music",),
            status="completed",
        )


class FakeTagGenerator:
    async def generate(self, request):
        return TagGenerationResult(
            paragraph_id=request.paragraph.paragraph_id,
            tags=("Harmony definition",),
            tagging_profile=request.tagging_profile,
        )


class FakeTagConflictResolver:
    async def resolve(self, request):
        return TagConflictResolution(
            paragraph_id=request.paragraph_id,
            generated_tags=request.generated_tags,
            existing_tags=tuple(candidate.tag for candidate in request.existing_tags),
            resolutions=tuple(
                TagResolution(tag, "keep_new", tag) for tag in request.generated_tags
            ),
            resolution_profile=request.resolution_profile,
        )


def settings() -> AppSettings:
    return AppSettings.from_environment(VALID_ENVIRONMENT)


def _artifact(artifact_id: str, kind: ArtifactKind, payload: bytes | None = None) -> ArtifactRef:
    import hashlib

    payload = artifact_id.encode() if payload is None else payload
    return ArtifactRef(
        artifact_id=artifact_id,
        version="v1",
        kind=kind,
        media_type="application/octet-stream",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
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


def test_document_process_route_persists_outputs_when_persistence_workflow_is_composed() -> None:
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
    artifacts = FakeArtifacts(b"source", puts=[])
    workflow = ProcessAndPersistDocument(
        ProcessDocument(artifacts, extractor), FakeExtractionPayloads(), artifacts
    )
    app = create_app(
        settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
            pdf_extractor=extractor,
            artifact_repository=artifacts,
            process_and_persist_document=workflow,
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
    assert [artifact.artifact_id for artifact, _ in artifacts.puts or []] == [
        "markdown",
        "layout",
        "manifest",
    ]


def test_process_and_ingest_route_runs_persisted_markdown_through_indexing() -> None:
    markdown = b"## Intro\nA source paragraph."
    result = PdfExtractionResult(
        document_ref="doc-1",
        source_version="source-v1",
        markdown=_artifact("markdown", ArtifactKind.MARKDOWN, markdown),
        layout=_artifact("layout", ArtifactKind.LAYOUT),
        manifest=_artifact("manifest", ArtifactKind.EXTRACTION_MANIFEST),
        coordinates=(),
        model_profile="extractor-v1",
    )
    extractor = FakePdfExtractor(result, [])
    artifacts = MultiArtifactRepository(
        {"source": b"source", "markdown": markdown},
        [],
    )
    vector_index = FakeVectorIndex()
    app = create_app(
        settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
            pdf_extractor=extractor,
            artifact_repository=artifacts,
            vector_index=vector_index,
            embedding_provider=FakeEmbeddingProvider(),
            process_and_persist_document=ProcessAndPersistDocument(
                ProcessDocument(artifacts, extractor),
                FakeExtractionPayloads(markdown),
                artifacts,
            ),
        ),
    )

    response = TestClient(app).post(
        "/api/v1/documents/doc-1/process-and-ingest",
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
            "chunking_profile": "header-v1",
            "embedding_profile": "embed-v1",
            "index_profile": "index-v1",
            "access_scope": "tenant-a",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ingestion"]["indexed"] is True
    assert body["ingestion"]["chunk_count"] == 1
    assert vector_index.records[0].search_text == "A source paragraph."


def test_process_and_ingest_route_preserves_tagging_before_indexing() -> None:
    markdown = b"## Intro\nA source paragraph."
    result = PdfExtractionResult(
        document_ref="doc-1",
        source_version="source-v1",
        markdown=_artifact("markdown", ArtifactKind.MARKDOWN, markdown),
        layout=_artifact("layout", ArtifactKind.LAYOUT),
        manifest=_artifact("manifest", ArtifactKind.EXTRACTION_MANIFEST),
        coordinates=(),
        model_profile="extractor-v1",
    )
    extractor = FakePdfExtractor(result, [])
    artifacts = MultiArtifactRepository({"source": b"source", "markdown": markdown}, [])
    vector_index = FakeVectorIndex()
    ingestion = IngestExtractedDocument(
        artifacts,
        ingest_document=IngestDocument(
            FakeTagAndPersist(),
            IndexDocument(vector_index, FakeEmbeddingProvider()),
        ),
    )
    app = create_app(
        settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
            pdf_extractor=extractor,
            artifact_repository=artifacts,
            ingest_extracted_document=ingestion,
            process_and_persist_document=ProcessAndPersistDocument(
                ProcessDocument(artifacts, extractor),
                FakeExtractionPayloads(markdown),
                artifacts,
            ),
        ),
    )

    response = TestClient(app).post(
        "/api/v1/documents/doc-1/process-and-ingest",
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
            "chunking_profile": "header-v1",
            "tagging_profile": "tags-v1",
            "resolution_profile": "resolve-v1",
            "embedding_profile": "embed-v1",
            "index_profile": "index-v1",
            "access_scope": "tenant-a",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ingestion"]["tagged_paragraph_count"] == 1
    assert vector_index.records[0].metadata["tags"] == ("music",)


def test_process_and_ingest_route_persists_tagged_paragraph_and_catalog(tmp_path) -> None:
    markdown = b"## Intro\nA source paragraph."
    result = PdfExtractionResult(
        document_ref="doc-1",
        source_version="source-v1",
        markdown=_artifact("markdown", ArtifactKind.MARKDOWN, markdown),
        layout=_artifact("layout", ArtifactKind.LAYOUT),
        manifest=_artifact("manifest", ArtifactKind.EXTRACTION_MANIFEST),
        coordinates=(),
        model_profile="extractor-v1",
    )
    extractor = FakePdfExtractor(result, [])
    artifacts = MultiArtifactRepository({"source": b"source", "markdown": markdown}, [])
    vector_index = FakeVectorIndex()
    tagged_repository = JsonTaggedParagraphRepository(tmp_path / "tagged-paragraphs")
    catalog_repository = JsonTagCatalogRepository(tmp_path / "tag-catalog.json")
    app = create_app(
        AppSettings.from_environment({**VALID_ENVIRONMENT, "SAXO_DATA_ROOT": str(tmp_path)}),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
            pdf_extractor=extractor,
            artifact_repository=artifacts,
            vector_index=vector_index,
            embedding_provider=FakeEmbeddingProvider(),
            tag_generator=FakeTagGenerator(),
            tag_conflict_resolver=FakeTagConflictResolver(),
            tagged_paragraph_repository=tagged_repository,
            tag_catalog_repository=catalog_repository,
            process_and_persist_document=ProcessAndPersistDocument(
                ProcessDocument(artifacts, extractor),
                FakeExtractionPayloads(markdown),
                artifacts,
            ),
        ),
    )

    response = TestClient(app).post(
        "/api/v1/documents/doc-1/process-and-ingest",
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
            "chunking_profile": "header-v1",
            "tagging_profile": "tags-v1",
            "resolution_profile": "resolve-v1",
            "embedding_profile": "embed-v1",
            "index_profile": "index-v1",
            "access_scope": "tenant-a",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ingestion"]["tagged_paragraph_count"] == 1
    assert asyncio.run(catalog_repository.list()) == ("Harmony definition",)
    sidecars = list((tmp_path / "tagged-paragraphs").glob("*.json"))
    assert len(sidecars) == 1
    assert json.loads(sidecars[0].read_text(encoding="utf-8"))["tags"] == [
        "Harmony definition",
    ]


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


def test_health_exposes_architecture_capabilities_without_provider_secrets() -> None:
    app = create_app(
        settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
            disable_vector_index=True,
        ),
    )

    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "app": "ready",
        "model_service": "ready",
        "remote_gpu": "ready",
        "remote_gpu_capabilities": ["chat"],
        "extraction": "ready",
        "ingestion": "disabled",
        "retrieval": "disabled",
        "chat": "disabled",
    }
    assert "secret-token" not in response.text


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


def test_document_ingest_route_indexes_chunks_and_returns_report() -> None:
    vector_index = FakeVectorIndex()
    embedding_provider = FakeEmbeddingProvider()
    app = create_app(
        settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
            embedding_provider=embedding_provider,
            vector_index=vector_index,
            embedding_reuse=InMemoryEmbeddingReuseStore(),
        ),
    )

    response = TestClient(app).post(
        "/api/v1/documents/doc-1/ingest",
        json={
            "source_version": "source-v1",
            "chunking_profile": "header-v1",
            "tagging_profile": "tags-v1",
            "embedding_profile": "embed-v1",
            "index_profile": "index-v1",
            "access_scope": "tenant-a",
            "records": [
                {
                    "chunk_id": "chunk-1",
                    "search_text": "A musical phrase",
                    "metadata": {"tags": ["phrase"]},
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["indexed"] is True
    assert response.json()["embedded_count"] == 1
    assert embedding_provider.calls == [
        ((("chunk-1", "A musical phrase"),), "source-v1"),
    ]
    assert vector_index.records[0].embedding == (0.9, 0.8)


def test_document_ingest_route_is_explicitly_unavailable_without_vector_index() -> None:
    app = create_app(
        settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
            disable_vector_index=True,
        ),
    )

    response = TestClient(app).post(
        "/api/v1/documents/doc-1/ingest",
        json={
            "source_version": "source-v1",
            "chunking_profile": "header-v1",
            "tagging_profile": "tags-v1",
            "embedding_profile": "embed-v1",
            "index_profile": "index-v1",
            "access_scope": "tenant-a",
            "records": [],
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "ingestion capability is not configured"}


def test_process_and_ingest_route_is_explicitly_unavailable_without_vector_index() -> None:
    app = create_app(
        settings(),
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            disable_vector_index=True,
        ),
    )

    response = TestClient(app).post(
        "/api/v1/documents/doc-1/process-and-ingest",
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
            "chunking_profile": "header-v1",
            "embedding_profile": "embed-v1",
            "index_profile": "index-v1",
            "access_scope": "public",
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "extracted document ingestion capability is not configured"}
