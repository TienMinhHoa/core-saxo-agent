"""Application use cases for publishing validated ingestion projections."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from .models import ChunkIndexRecord, EmbeddingRecord, IngestionCommand, IngestionReport
from .ports import EmbeddingProvider, VectorIndex


class IndexDocument:
    """Publish one document's searchable chunks through the vector-index port."""

    def __init__(self, vector_index: VectorIndex, embedding_provider: EmbeddingProvider) -> None:
        self._vector_index = vector_index
        self._embedding_provider = embedding_provider

    async def execute(
        self,
        command: IngestionCommand,
        records: Sequence[ChunkIndexRecord],
    ) -> IngestionReport:
        normalized_records = tuple(records)
        self._validate_scope(command, normalized_records)
        tagged_count = sum(1 for record in normalized_records if record.metadata.get("tags"))
        try:
            embedded_records = await self._embed_records(command, normalized_records)
        except Exception as error:
            return self._failure_report(
                command,
                normalized_records,
                tagged_count=tagged_count,
                embedded_count=0,
                error=error,
            )
        try:
            await self._vector_index.upsert_chunks(embedded_records)
        except Exception as error:
            return self._failure_report(
                command,
                normalized_records,
                tagged_count=tagged_count,
                embedded_count=len(embedded_records),
                error=error,
            )
        return IngestionReport(
            document_ref=command.document_ref,
            source_version=command.source_version,
            chunk_count=len(normalized_records),
            paragraph_count=len(normalized_records),
            tagged_paragraph_count=tagged_count,
            failed_paragraph_count=0,
            embedded_count=len(normalized_records),
            reused_embedding_count=0,
            skipped_count=0,
            index_version=command.index_profile,
            indexed=True,
            warnings=(),
            errors=(),
        )

    async def _embed_records(
        self,
        command: IngestionCommand,
        records: Sequence[ChunkIndexRecord],
    ) -> tuple[ChunkIndexRecord, ...]:
        embeddings = await self._embedding_provider.embed(
            tuple((record.chunk_id, record.search_text) for record in records),
            source_version=command.source_version,
        )
        if len(embeddings) != len(records):
            raise ValueError("embedding count does not match chunk count")
        embedded: list[ChunkIndexRecord] = []
        for record, embedding in zip(records, embeddings):
            self._validate_embedding(command, record, embedding)
            embedded.append(replace(record, embedding=embedding.vector))
        return tuple(embedded)

    @staticmethod
    def _validate_embedding(
        command: IngestionCommand,
        record: ChunkIndexRecord,
        embedding: EmbeddingRecord,
    ) -> None:
        if embedding.chunk_id != record.chunk_id:
            raise ValueError("embedding chunk ID does not match record")
        if embedding.source_version != command.source_version:
            raise ValueError("embedding source version does not match command")
        if embedding.model_profile != command.embedding_profile:
            raise ValueError("embedding model profile does not match command")

    @staticmethod
    def _failure_report(
        command: IngestionCommand,
        records: Sequence[ChunkIndexRecord],
        *,
        tagged_count: int,
        embedded_count: int,
        error: Exception,
    ) -> IngestionReport:
        return IngestionReport(
            document_ref=command.document_ref,
            source_version=command.source_version,
            chunk_count=len(records),
            paragraph_count=len(records),
            tagged_paragraph_count=tagged_count,
            failed_paragraph_count=len(records),
            embedded_count=embedded_count,
            reused_embedding_count=0,
            skipped_count=0,
            index_version=command.index_profile,
            indexed=False,
            warnings=(),
            errors=(str(error),),
        )

    @staticmethod
    def _validate_scope(
        command: IngestionCommand,
        records: Sequence[ChunkIndexRecord],
    ) -> None:
        for record in records:
            if record.document_ref != command.document_ref:
                raise ValueError("all records must belong to the command document")
            if record.source_version != command.source_version:
                raise ValueError("all records must match the command source version")
            if record.embedding_profile != command.embedding_profile:
                raise ValueError("all records must match the command embedding profile")
            if record.access_scope != command.access_scope:
                raise ValueError("all records must match the command access scope")
