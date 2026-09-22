"""Workflow for publishing persisted extraction Markdown to the index."""

from __future__ import annotations

from uuid import uuid4

from saxophone.documents import ArtifactRepository
from saxophone.extraction import PdfExtractionResult
from saxophone.ingestion import (
    DocumentIngestionService,
    IndexDocument,
    IndexInputRecord,
    IngestDocument,
    IngestionCommand,
    build_source_chunks,
)
from saxophone.tagging import parse_chunk_paragraphs


class IngestExtractedDocument:
    """Read verified Markdown and delegate to the selected ingestion boundary.

    Extraction persistence remains separate. The compatibility mode projects
    directly to ``IndexDocument``; the preferred mode parses paragraphs and
    delegates tagging, persistence, embedding, and indexing to ``IngestDocument``.
    """

    def __init__(
        self,
        artifacts: ArtifactRepository,
        index_document: IndexDocument | None = None,
        *,
        ingest_document: IngestDocument | None = None,
        document_ingestion: DocumentIngestionService | None = None,
    ) -> None:
        if index_document is None and ingest_document is None:
            raise ValueError("an index or ingestion workflow must be configured")
        if document_ingestion is not None and ingest_document is None:
            raise ValueError("document ingestion requires an ingest workflow")
        if document_ingestion is not None and not callable(
            getattr(document_ingestion, "ingest_document", None)
        ):
            raise TypeError("document ingestion must provide ingest_document")
        self._artifacts = artifacts
        self._index_document = index_document
        self._ingest_document = ingest_document
        self._document_ingestion = document_ingestion

    async def execute(
        self,
        result: PdfExtractionResult,
        *,
        chunking_profile: str,
        embedding_profile: str,
        index_profile: str,
        access_scope: str,
        tagging_profile: str = "none-v1",
        resolution_profile: str = "none-v1",
        ingestion_run_id: str | None = None,
        sync_limit: int = 100,
    ):
        _validate_optional_ingestion_run_id(ingestion_run_id)
        _validate_sync_limit(sync_limit)
        if chunking_profile != "header-v1":
            raise ValueError(f"unsupported chunking profile: {chunking_profile}")
        markdown = await self._artifacts.get(result.markdown)
        try:
            markdown_text = markdown.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("persisted extraction Markdown must be UTF-8") from error

        command = IngestionCommand(
            document_ref=result.document_ref,
            source_version=result.source_version,
            chunking_profile=chunking_profile,
            tagging_profile="none-v1",
            embedding_profile=embedding_profile,
            index_profile=index_profile,
            access_scope=access_scope,
        )
        chunks = build_source_chunks(
            markdown_text,
            document_ref=result.document_ref,
            source_version=result.source_version,
            access_scope=access_scope,
        )
        if tagging_profile != "none-v1" and self._ingest_document is None:
            raise ValueError("tagging workflow is required for a non-none tagging profile")
        if self._ingest_document is not None and tagging_profile != "none-v1":
            paragraphs = tuple(
                paragraph
                for chunk in chunks
                for paragraph in parse_chunk_paragraphs(chunk)
            )
            command = IngestionCommand(
                document_ref=result.document_ref,
                source_version=result.source_version,
                chunking_profile=chunking_profile,
                tagging_profile=tagging_profile,
                embedding_profile=embedding_profile,
                index_profile=index_profile,
                access_scope=access_scope,
            )
            if self._document_ingestion is not None:
                return await self._document_ingestion.ingest_document(
                    command,
                    chunks,
                    paragraphs,
                    resolution_profile=resolution_profile,
                    sync_limit=sync_limit,
                    ingestion_run_id=ingestion_run_id or _new_ingestion_run_id(),
                    source_hash=result.markdown.sha256,
                )
            return await self._ingest_document.execute(
                command,
                chunks,
                paragraphs,
                resolution_profile=resolution_profile,
            )
        assert self._index_document is not None
        records = tuple(
            IndexInputRecord(
                chunk_id=chunk.chunk_id,
                document_ref=chunk.document_ref,
                source_version=chunk.source_version,
                search_text=chunk.search_text,
                embedding_profile=embedding_profile,
                access_scope=chunk.access_scope,
                metadata={**chunk.metadata, "tags": ()},
            )
            for chunk in chunks
        )
        return await self._index_document.execute(command, records)


def _new_ingestion_run_id() -> str:
    """Create a fresh run identity; callers can pass one explicitly to resume."""

    return f"ingest-{uuid4().hex}"


def _validate_optional_ingestion_run_id(value: str | None) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError("ingestion_run_id must be blank or null")


def _validate_sync_limit(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("sync_limit must be positive")
