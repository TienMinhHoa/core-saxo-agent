from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pytest

from saxophone.app.factory import AppOverrides, create_app
from saxophone.app.settings import AppSettings
from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.documents.ports import ArtifactRepository
from saxophone.extraction.models import PdfExtractionResult
from saxophone.ingestion.models import IngestionReport
from saxophone.ingestion.services import DocumentIngestionService
from saxophone.ingestion.state import SqliteIngestionStateRepository
from saxophone.ingestion.vector_state import SqliteVectorIndexStateRepository
from saxophone.ingestion.vector_sync import VectorSyncService
from saxophone.tagging.vector_outbox import SqliteVectorOutboxRepository
from saxophone.workflows.ingest_extracted_document import IngestExtractedDocument


VALID_ENVIRONMENT = {
    "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
    "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
}


def _artifact(kind: ArtifactKind, artifact_id: str, payload: bytes) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        version="v1",
        kind=kind,
        media_type="application/octet-stream",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def _result(markdown: bytes = b"## Intro\nA source paragraph.") -> PdfExtractionResult:
    return PdfExtractionResult(
        document_ref="doc-1",
        source_version="source-v1",
        markdown=_artifact(ArtifactKind.MARKDOWN, "markdown", markdown),
        layout=_artifact(ArtifactKind.LAYOUT, "layout", b"layout"),
        manifest=_artifact(ArtifactKind.EXTRACTION_MANIFEST, "manifest", b"manifest"),
        coordinates=(),
        model_profile="extract-v1",
    )


@dataclass
class FakeArtifacts(ArtifactRepository):
    payloads: dict[str, bytes]

    async def put(self, artifact: ArtifactRef, payload: bytes) -> None:
        self.payloads[artifact.artifact_id] = payload

    async def get(self, artifact: ArtifactRef) -> bytes:
        return self.payloads[artifact.artifact_id]


@dataclass
class RecordingDocumentIngestion:
    calls: list[dict[str, object]]

    async def ingest_document(self, command, chunks, paragraphs, **kwargs):
        self.calls.append(
            {
                "command": command,
                "chunks": tuple(chunks),
                "paragraphs": tuple(paragraphs),
                **kwargs,
            }
        )
        return IngestionReport(
            document_ref=command.document_ref,
            source_version=command.source_version,
            chunk_count=len(chunks),
            paragraph_count=len(paragraphs),
            tagged_paragraph_count=len(paragraphs),
            failed_paragraph_count=0,
            embedded_count=1,
            reused_embedding_count=0,
            skipped_count=0,
            index_version=command.index_profile,
            indexed=True,
            warnings=(),
            errors=(),
        )


class FakeIngestWorkflow:
    async def execute(self, *args, **kwargs):
        raise AssertionError("outer document ingestion service should own execution")


class FakeRemoteGpuGateway:
    async def health(self):
        raise AssertionError("composition test must not probe the provider")


class FakeModelClient:
    async def invoke(self, request):
        raise AssertionError("composition test must not invoke the provider")


class FakeVectorIndex:
    async def upsert_chunks(self, records) -> None:
        return None

    async def delete_chunks(self, chunk_ids) -> None:
        return None


@pytest.mark.anyio
async def test_extracted_document_delegates_chunk_ingestion_to_outer_coordinator() -> None:
    markdown = b"## Intro\nA source paragraph."
    coordinator = RecordingDocumentIngestion([])
    workflow = IngestExtractedDocument(
        FakeArtifacts({"markdown": markdown}),
        ingest_document=FakeIngestWorkflow(),
        document_ingestion=coordinator,
    )

    result = await workflow.execute(
        _result(markdown),
        chunking_profile="header-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
        tagging_profile="tags-v1",
        resolution_profile="resolve-v1",
        ingestion_run_id="run-57",
    )

    assert result.indexed is True
    assert len(coordinator.calls) == 1
    call = coordinator.calls[0]
    assert call["ingestion_run_id"] == "run-57"
    assert call["source_hash"] == _result(markdown).markdown.sha256
    assert call["command"].tagging_profile == "tags-v1"
    assert len(call["chunks"]) == 1
    assert len(call["paragraphs"]) == 1


@pytest.mark.anyio
async def test_extracted_document_generates_fresh_run_ids_and_validates_sync_limit() -> None:
    markdown = b"## Intro\nA source paragraph."
    coordinator = RecordingDocumentIngestion([])
    workflow = IngestExtractedDocument(
        FakeArtifacts({"markdown": markdown}),
        ingest_document=FakeIngestWorkflow(),
        document_ingestion=coordinator,
    )

    await workflow.execute(
        _result(markdown),
        chunking_profile="header-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
        tagging_profile="tags-v1",
        resolution_profile="resolve-v1",
    )
    await workflow.execute(
        _result(markdown),
        chunking_profile="header-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
        tagging_profile="tags-v1",
        resolution_profile="resolve-v1",
    )

    run_ids = [call["ingestion_run_id"] for call in coordinator.calls]
    assert all(isinstance(run_id, str) and run_id.startswith("ingest-") for run_id in run_ids)
    assert len(set(run_ids)) == 2

    with pytest.raises(ValueError, match="sync_limit must be positive"):
        await workflow.execute(
            _result(markdown),
            chunking_profile="header-v1",
            embedding_profile="embed-v1",
            index_profile="index-v1",
            access_scope="tenant-a",
            tagging_profile="tags-v1",
            resolution_profile="resolve-v1",
            sync_limit=0,
        )


def test_chunk_tagging_composition_builds_outer_document_ingestion_service(
    tmp_path: Path,
) -> None:
    settings = AppSettings.from_environment(
        {
            **VALID_ENVIRONMENT,
            "SAXO_DATA_ROOT": str(tmp_path),
            "SAXO_CHUNK_TAGGING_ENABLED": "true",
        }
    )
    app = create_app(
        settings,
        overrides=AppOverrides(
            model_client=FakeModelClient(),
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            vector_index=FakeVectorIndex(),
        ),
    )

    container = app.state.container

    assert isinstance(container.document_ingestion, DocumentIngestionService)
    assert isinstance(container.document_ingestion._vector_sync, VectorSyncService)
    assert isinstance(
        container.document_ingestion._vector_sync._outbox,
        SqliteVectorOutboxRepository,
    )
    assert isinstance(
        container.document_ingestion._lifecycle,
        SqliteIngestionStateRepository,
    )
    assert isinstance(
        container.document_ingestion._ingest_workflow._vector_state,
        SqliteVectorIndexStateRepository,
    )
    assert container.ingest_extracted_document is not None
    assert container.ingest_extracted_document._document_ingestion is container.document_ingestion
