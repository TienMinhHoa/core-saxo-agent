from __future__ import annotations

import math

import pytest

from saxophone.ingestion.models import (
    EmbeddingRecord,
    IngestionCommand,
    IngestionReport,
)


def test_ingestion_command_contains_profiles_and_scope() -> None:
    command = IngestionCommand(
        document_ref="document-1",
        source_version="extract-v1",
        chunking_profile="heading-chunks-v1",
        tagging_profile="topic-tags-v1",
        embedding_profile="embed-v1",
        index_profile="chroma-v1",
        access_scope="private",
    )

    assert command.document_ref == "document-1"
    assert command.index_profile == "chroma-v1"


def test_embedding_record_requires_dimension_and_finite_values() -> None:
    record = EmbeddingRecord(
        chunk_id="chunk-1",
        source_version="extract-v1",
        model_profile="embed-v1",
        vector=(0.1, -0.2),
    )

    assert record.dimension == 2
    assert record.vector == (0.1, -0.2)

    with pytest.raises(ValueError, match="finite"):
        EmbeddingRecord(
            chunk_id="chunk-1",
            source_version="extract-v1",
            model_profile="embed-v1",
            vector=(math.nan,),
        )


def test_embedding_record_rejects_empty_vector() -> None:
    with pytest.raises(ValueError, match="vector"):
        EmbeddingRecord(
            chunk_id="chunk-1",
            source_version="extract-v1",
            model_profile="embed-v1",
            vector=(),
        )


def test_ingestion_report_cannot_mark_partial_index_as_complete() -> None:
    with pytest.raises(ValueError, match="failed_count"):
        IngestionReport(
            document_ref="document-1",
            source_version="extract-v1",
            chunk_count=3,
            paragraph_count=4,
            tagged_paragraph_count=3,
            failed_paragraph_count=1,
            embedded_count=2,
            reused_embedding_count=0,
            skipped_count=0,
            index_version="chroma-v1",
            indexed=True,
            warnings=(),
            errors=(),
        )


def test_ingestion_report_accepts_complete_zero_error_run() -> None:
    report = IngestionReport(
        document_ref="document-1",
        source_version="extract-v1",
        chunk_count=3,
        paragraph_count=4,
        tagged_paragraph_count=4,
        failed_paragraph_count=0,
        embedded_count=3,
        reused_embedding_count=1,
        skipped_count=0,
        index_version="chroma-v1",
        indexed=True,
        warnings=(),
        errors=(),
    )

    assert report.indexed is True
    assert report.reused_embedding_count == 1
