"""Workflow for publishing persisted extraction Markdown to the index."""

from __future__ import annotations

from saxophone.documents.ports import ArtifactRepository
from saxophone.extraction.models import PdfExtractionResult
from saxophone.ingestion.chunking import build_source_chunks
from saxophone.ingestion.models import IndexInputRecord, IngestionCommand
from saxophone.ingestion.use_cases import IndexDocument


class IngestExtractedDocument:
    """Read verified Markdown output and delegate indexing to the ingestion use case.

    Extraction persistence and indexing remain separate boundaries: this workflow
    only performs the deterministic Markdown-to-index-input projection.
    """

    def __init__(self, artifacts: ArtifactRepository, index_document: IndexDocument) -> None:
        self._artifacts = artifacts
        self._index_document = index_document

    async def execute(
        self,
        result: PdfExtractionResult,
        *,
        chunking_profile: str,
        embedding_profile: str,
        index_profile: str,
        access_scope: str,
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
