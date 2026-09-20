"""Workflow for publishing persisted extraction Markdown to the index."""

from __future__ import annotations

from saxophone.documents.ports import ArtifactRepository
from saxophone.extraction.models import PdfExtractionResult
from saxophone.ingestion.chunking import build_source_chunks
from saxophone.ingestion.models import IndexInputRecord, IngestionCommand
from saxophone.ingestion.use_cases import IngestDocument, IndexDocument
from saxophone.tagging.parser import parse_chunk_paragraphs


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
    ) -> None:
        if index_document is None and ingest_document is None:
            raise ValueError("an index or ingestion workflow must be configured")
        if index_document is not None and ingest_document is not None:
            raise ValueError("configure either index or ingestion workflow, not both")
        self._artifacts = artifacts
        self._index_document = index_document
        self._ingest_document = ingest_document

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
    ):
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
        if self._ingest_document is not None:
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
