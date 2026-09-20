from __future__ import annotations

import pytest

from saxophone.ingestion.models import ChunkIndexRecord, IngestionCommand
from saxophone.ingestion.use_cases import IndexDocument


def _command() -> IngestionCommand:
    return IngestionCommand(
        document_ref="doc-1",
        source_version="source-v1",
        chunking_profile="header-v1",
        tagging_profile="tags-v1",
        embedding_profile="embed-v1",
        index_profile="index-v1",
        access_scope="tenant-a",
    )


def _record(
    document_ref: str = "doc-1",
    source_version: str = "source-v1",
    embedding_profile: str = "embed-v1",
    access_scope: str = "tenant-a",
) -> ChunkIndexRecord:
    return ChunkIndexRecord(
        chunk_id="chunk-1",
        document_ref=document_ref,
        source_version=source_version,
        search_text="A musical phrase",
        embedding=(0.1, 0.2),
        embedding_profile=embedding_profile,
        access_scope=access_scope,
        metadata={"tags": ["phrase"]},
    )


class FakeIndex:
    def __init__(self, error: Exception | None = None) -> None:
        self.records = None
        self.error = error

    async def upsert_chunks(self, records):
        if self.error:
            raise self.error
        self.records = tuple(records)


@pytest.mark.anyio
async def test_index_document_publishes_records_and_report() -> None:
    index = FakeIndex()

    report = await IndexDocument(index).execute(_command(), [_record()])

    assert index.records == (_record(),)
    assert report.indexed is True
    assert report.chunk_count == 1
    assert report.tagged_paragraph_count == 1
    assert report.errors == ()


@pytest.mark.anyio
async def test_index_document_reports_partial_failure_without_claiming_indexed() -> None:
    index = FakeIndex(RuntimeError("vector store unavailable"))

    report = await IndexDocument(index).execute(_command(), [_record()])

    assert report.indexed is False
    assert report.failed_paragraph_count == 1
    assert report.errors == ("vector store unavailable",)


@pytest.mark.anyio
async def test_index_document_rejects_cross_document_records_before_index_call() -> None:
    index = FakeIndex()

    with pytest.raises(ValueError, match="document"):
        await IndexDocument(index).execute(_command(), [_record(document_ref="other")])

    assert index.records is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("embedding_profile", "embed-v2", "embedding profile"),
        ("access_scope", "tenant-b", "access scope"),
    ],
)
async def test_index_document_rejects_records_with_incompatible_index_context(
    field: str, value: str, message: str
) -> None:
    index = FakeIndex()

    with pytest.raises(ValueError, match=message):
        await IndexDocument(index).execute(_command(), [_record(**{field: value})])

    assert index.records is None
