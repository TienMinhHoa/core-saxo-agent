from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pytest

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.documents.knowledge import KnowledgeChunk
from saxophone.documents.ports import ArtifactRepository
from saxophone.extraction.models import PdfExtractionResult
from saxophone.ingestion.models import EmbeddingRecord
from saxophone.ingestion.use_cases import IngestDocument
from saxophone.ingestion.use_cases import IndexDocument
from saxophone.tagging.models import TaggedParagraph
from saxophone.workflows.ingest_extracted_document import IngestExtractedDocument


def _artifact(kind: ArtifactKind, artifact_id: str, payload: bytes) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        version="v1",
        kind=kind,
        media_type="application/octet-stream",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def _result(markdown: bytes = b"# ignored\n## Intro\nA source paragraph.") -> PdfExtractionResult:
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


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[tuple[str, str], ...], str]] = []

    async def embed(self, chunks, *, source_version: str):
        normalized = tuple(chunks)
        self.calls.append((normalized, source_version))
        return tuple(
            EmbeddingRecord(
                chunk_id=chunk_id,
                source_version=source_version,
                model_profile="embed-v1",
                vector=(0.1, 0.2),
            )
            for chunk_id, _ in normalized
        )


class FakeVectorIndex:
    def __init__(self) -> None:
        self.records = ()

    async def upsert_chunks(self, records) -> None:
        self.records = tuple(records)

    async def delete_chunks(self, chunk_ids) -> None:
        raise AssertionError("not used")

    async def search(self, query_vector, *, filters=None, limit=10):
        raise AssertionError("not used")


class FakeKnowledgeRepository:
    def __init__(self) -> None:
        self.chunks: list[KnowledgeChunk] = []

    async def upsert(self, chunk: KnowledgeChunk) -> None:
        self.chunks.append(chunk)

    async def get(self, chunk_id: str) -> KnowledgeChunk:
        return next(chunk for chunk in self.chunks if chunk.chunk_id == chunk_id)

    async def delete(self, chunk_id: str) -> None:
        self.chunks = [chunk for chunk in self.chunks if chunk.chunk_id != chunk_id]


class FakeTagAndPersist:
    async def execute(self, paragraph, *, tagging_profile, resolution_profile):
        return TaggedParagraph(
            paragraph_id=paragraph.paragraph_id,
            text=paragraph.text,
            generated_tags=("music",),
            tags=("music",),
            status="completed",
        )


@pytest.mark.anyio
async def test_ingest_extracted_document_builds_index_inputs_from_persisted_markdown() -> None:
    markdown = b"# ignored\n## Intro\nA source paragraph."
    artifacts = FakeArtifacts({"markdown": markdown})
    embeddings = FakeEmbeddingProvider()
    index = FakeVectorIndex()
    workflow = IngestExtractedDocument(
        artifacts,
        IndexDocument(index, embeddings),
    )

    report = await workflow.execute(
        _result(markdown),
        chunking_profile="header-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
    )

    assert report.indexed is True
    assert report.chunk_count == 1
    assert len(index.records) == 1
    assert index.records[0].search_text == "A source paragraph."
    assert index.records[0].metadata["tags"] == ()
    assert embeddings.calls[0][0][0][1] == "A source paragraph."


@pytest.mark.anyio
async def test_index_document_persists_knowledge_before_vector_upsert() -> None:
    knowledge = FakeKnowledgeRepository()
    index = FakeVectorIndex()
    workflow = IngestExtractedDocument(
        FakeArtifacts({"markdown": b"## Harmony\nA source paragraph."}),
        IndexDocument(index, FakeEmbeddingProvider(), knowledge_repository=knowledge),
    )

    report = await workflow.execute(
        _result(b"## Harmony\nA source paragraph."),
        chunking_profile="header-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
    )

    assert report.indexed is True
    assert len(knowledge.chunks) == 1
    stored = knowledge.chunks[0]
    assert stored.chunk_id == index.records[0].chunk_id
    assert stored.document_id == "doc-1"
    assert stored.source_version == "source-v1"
    assert stored.search_text == "A source paragraph."
    assert stored.heading_path == ("Harmony",)
    assert stored.content_hash == hashlib.sha256(stored.search_text.encode()).hexdigest()


@pytest.mark.anyio
async def test_index_document_does_not_index_when_knowledge_persistence_fails() -> None:
    class FailingKnowledgeRepository(FakeKnowledgeRepository):
        async def upsert(self, chunk: KnowledgeChunk) -> None:
            raise RuntimeError("knowledge store unavailable")

    index = FakeVectorIndex()
    workflow = IngestExtractedDocument(
        FakeArtifacts({"markdown": b"## Intro\nsource"}),
        IndexDocument(
            index,
            FakeEmbeddingProvider(),
            knowledge_repository=FailingKnowledgeRepository(),
        ),
    )

    report = await workflow.execute(
        _result(b"## Intro\nsource"),
        chunking_profile="header-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
    )

    assert report.indexed is False
    assert report.errors == ("knowledge store unavailable",)
    assert index.records == ()


@pytest.mark.anyio
async def test_ingest_extracted_document_rejects_unsupported_chunking_profile() -> None:
    workflow = IngestExtractedDocument(
        FakeArtifacts({"markdown": b"## Intro\ntext"}),
        IndexDocument(FakeVectorIndex(), FakeEmbeddingProvider()),
    )

    with pytest.raises(ValueError, match="unsupported chunking profile"):
        await workflow.execute(
            _result(b"## Intro\ntext"),
            chunking_profile="unknown-v1",
            embedding_profile="embed-v1",
            index_profile="index-v1",
            access_scope="tenant-a",
        )


@pytest.mark.anyio
async def test_ingest_extracted_document_can_run_paragraph_tagging_before_indexing() -> None:
    markdown = b"# ignored\n## Intro\nA source paragraph."
    index = FakeVectorIndex()
    workflow = IngestExtractedDocument(
        FakeArtifacts({"markdown": markdown}),
        ingest_document=IngestDocument(
            FakeTagAndPersist(),
            IndexDocument(index, FakeEmbeddingProvider()),
        ),
    )

    report = await workflow.execute(
        _result(markdown),
        chunking_profile="header-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
        tagging_profile="tags-v1",
        resolution_profile="resolve-v1",
    )

    assert report.tagged_paragraph_count == 1
    assert index.records[0].metadata["tags"] == ("music",)


@pytest.mark.anyio
async def test_ingest_extracted_document_rejects_tagging_without_tagging_workflow() -> None:
    workflow = IngestExtractedDocument(
        FakeArtifacts({"markdown": b"## Intro\ntext"}),
        IndexDocument(FakeVectorIndex(), FakeEmbeddingProvider()),
    )

    with pytest.raises(ValueError, match="tagging workflow"):
        await workflow.execute(
            _result(b"## Intro\ntext"),
            chunking_profile="header-v1",
            embedding_profile="embed-v1",
            index_profile="index-v1",
            access_scope="tenant-a",
            tagging_profile="tags-v1",
            resolution_profile="resolve-v1",
        )
