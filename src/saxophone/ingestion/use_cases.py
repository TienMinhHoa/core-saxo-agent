"""Application use cases for publishing validated ingestion projections."""

from __future__ import annotations

from collections.abc import Sequence

from .models import ChunkIndexRecord, IngestionCommand, IngestionReport
from .ports import VectorIndex


class IndexDocument:
    """Publish one document's searchable chunks through the vector-index port."""

    def __init__(self, vector_index: VectorIndex) -> None:
        self._vector_index = vector_index

    async def execute(
        self,
        command: IngestionCommand,
        records: Sequence[ChunkIndexRecord],
    ) -> IngestionReport:
        normalized_records = tuple(records)
        self._validate_scope(command, normalized_records)
        tagged_count = sum(1 for record in normalized_records if record.metadata.get("tags"))
        try:
            await self._vector_index.upsert_chunks(normalized_records)
        except Exception as error:
            return IngestionReport(
                document_ref=command.document_ref,
                source_version=command.source_version,
                chunk_count=len(normalized_records),
                paragraph_count=len(normalized_records),
                tagged_paragraph_count=tagged_count,
                failed_paragraph_count=len(normalized_records),
                embedded_count=len(normalized_records),
                reused_embedding_count=0,
                skipped_count=0,
                index_version=command.index_profile,
                indexed=False,
                warnings=(),
                errors=(str(error),),
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

