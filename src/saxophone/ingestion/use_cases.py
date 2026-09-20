"""Application use cases for publishing validated ingestion projections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from saxophone.tagging.models import TaggedParagraph

from .models import (
    ChunkIndexRecord,
    EmbeddingRecord,
    IndexInputRecord,
    IngestionCommand,
    IngestionReport,
    IngestionSourceChunk,
)
from .ports import EmbeddingProvider, VectorIndex


class IndexDocument:
    """Publish one document's searchable chunks through the vector-index port."""

    def __init__(self, vector_index: VectorIndex, embedding_provider: EmbeddingProvider) -> None:
        self._vector_index = vector_index
        self._embedding_provider = embedding_provider

    async def execute(
        self,
        command: IngestionCommand,
        records: Sequence[IndexInputRecord],
    ) -> IngestionReport:
        normalized_records = tuple(records)
        self._validate_scope(command, normalized_records)
        tagged_count = sum(1 for record in normalized_records if record.metadata.get("tags"))
        try:
            indexed_records = await self._embed_records(command, normalized_records)
        except Exception as error:
            return self._failure_report(
                command,
                normalized_records,
                tagged_count=tagged_count,
                embedded_count=0,
                error=error,
            )
        try:
            await self._vector_index.upsert_chunks(indexed_records)
        except Exception as error:
            return self._failure_report(
                command,
                normalized_records,
                tagged_count=tagged_count,
                embedded_count=len(indexed_records),
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
        records: Sequence[IndexInputRecord],
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
            embedded.append(
                ChunkIndexRecord(
                    chunk_id=record.chunk_id,
                    document_ref=record.document_ref,
                    source_version=record.source_version,
                    search_text=record.search_text,
                    embedding=embedding.vector,
                    embedding_profile=record.embedding_profile,
                    access_scope=record.access_scope,
                    metadata=record.metadata,
                )
            )
        return tuple(embedded)

    @staticmethod
    def _validate_embedding(
        command: IngestionCommand,
        record: IndexInputRecord,
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
        records: Sequence[IndexInputRecord],
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
        records: Sequence[IndexInputRecord],
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


def build_index_inputs(
    command: IngestionCommand,
    chunks: Sequence[IngestionSourceChunk],
    tagged_paragraphs: Mapping[str, TaggedParagraph],
) -> tuple[IndexInputRecord, ...]:
    """Project tagged source chunks into embedding-ready records.

    Paragraph persistence remains separate from this projection. Tags are
    copied into chunk metadata in deterministic paragraph order, while source
    text is kept byte-for-byte as produced by chunking.
    """
    inputs: list[IndexInputRecord] = []
    for chunk in chunks:
        _validate_chunk_scope(command, chunk)
        related = sorted(
            (
                paragraph
                for paragraph_id, paragraph in tagged_paragraphs.items()
                if paragraph_id.startswith(f"{chunk.chunk_id}:p")
            ),
            key=lambda paragraph: paragraph.paragraph_id,
        )
        unknown = [
            paragraph_id
            for paragraph_id in tagged_paragraphs
            if paragraph_id.startswith(f"{chunk.chunk_id}:")
            and paragraph_id not in {paragraph.paragraph_id for paragraph in related}
        ]
        if unknown:
            raise ValueError("tagged paragraph map contains an invalid paragraph projection")
        tags = tuple(dict.fromkeys(tag for paragraph in related for tag in paragraph.tags))
        metadata = dict(chunk.metadata)
        metadata["tags"] = tags
        metadata["tagged_paragraph_ids"] = tuple(paragraph.paragraph_id for paragraph in related)
        inputs.append(
            IndexInputRecord(
                chunk_id=chunk.chunk_id,
                document_ref=chunk.document_ref,
                source_version=chunk.source_version,
                search_text=chunk.search_text,
                embedding_profile=command.embedding_profile,
                access_scope=chunk.access_scope,
                metadata=metadata,
            )
        )
    return tuple(inputs)


def _validate_chunk_scope(command: IngestionCommand, chunk: IngestionSourceChunk) -> None:
    if chunk.document_ref != command.document_ref:
        raise ValueError("all chunks must belong to the command document")
    if chunk.source_version != command.source_version:
        raise ValueError("all chunks must match the command source version")
    if chunk.access_scope != command.access_scope:
        raise ValueError("all chunks must match the command access scope")
