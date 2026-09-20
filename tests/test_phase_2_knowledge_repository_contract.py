from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace

import pytest

from saxophone.documents.knowledge import KnowledgeChunk
from saxophone.documents.ports import KnowledgeRepository


class InMemoryKnowledgeRepository:
    def __init__(self) -> None:
        self._chunks: dict[str, KnowledgeChunk] = {}

    async def upsert(self, chunk: KnowledgeChunk) -> None:
        self._chunks[chunk.chunk_id] = chunk

    async def get(self, chunk_id: str) -> KnowledgeChunk:
        try:
            return self._chunks[chunk_id]
        except KeyError as error:
            raise FileNotFoundError(chunk_id) from error

    async def delete(self, chunk_id: str) -> None:
        try:
            del self._chunks[chunk_id]
        except KeyError as error:
            raise FileNotFoundError(chunk_id) from error


def _chunk(*, chunk_id: str = "chunk-1") -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=chunk_id,
        document_id="document-1",
        source_version="extract-v1",
        source_ref="knowledge://document-1/chunk-1",
        search_text="Harmony and chord construction",
        content_hash=hashlib.sha256(b"chunk").hexdigest(),
        page_start=2,
        page_end=3,
        heading_path=("Part III", "Harmony"),
        tags=("chord",),
        image_refs=("images/page-0002-01.jpg",),
        paragraph_count=2,
        image_count=1,
    )


def test_knowledge_repository_port_round_trips_and_replaces_chunks() -> None:
    repository: KnowledgeRepository = InMemoryKnowledgeRepository()
    original = _chunk()
    replacement = replace(original, search_text="Updated source text")

    asyncio.run(repository.upsert(original))
    assert asyncio.run(repository.get(original.chunk_id)) == original
    asyncio.run(repository.upsert(replacement))
    assert asyncio.run(repository.get(original.chunk_id)).search_text == "Updated source text"


def test_knowledge_repository_reports_missing_chunks() -> None:
    repository: KnowledgeRepository = InMemoryKnowledgeRepository()

    with pytest.raises(FileNotFoundError):
        asyncio.run(repository.get("missing"))
    with pytest.raises(FileNotFoundError):
        asyncio.run(repository.delete("missing"))


@pytest.mark.parametrize(
    ("field", "value"),
    [("search_text", "  "), ("content_hash", "not-a-hash")],
)
def test_knowledge_chunk_rejects_invalid_source_contract(field: str, value: str) -> None:
    fields = {
        "chunk_id": "chunk-1",
        "document_id": "document-1",
        "source_version": "extract-v1",
        "source_ref": "knowledge://document-1/chunk-1",
        "search_text": "source",
        "content_hash": hashlib.sha256(b"chunk").hexdigest(),
    }
    fields[field] = value

    with pytest.raises(ValueError, match=field):
        KnowledgeChunk(**fields)


@pytest.mark.parametrize(
    "source_ref",
    [
        " knowledge://document-1/chunk-1",
        "knowledge://document-1/chunk-1\n",
        "knowledge://document-cafe\u0301/chunk-1",
    ],
)
def test_knowledge_chunk_rejects_non_canonical_source_reference(source_ref: str) -> None:
    with pytest.raises(ValueError, match="source_ref"):
        replace(_chunk(), source_ref=source_ref)


@pytest.mark.parametrize(
    "image_ref",
    ["../secret.png", "/absolute.png", "https://example.test/a.png", "images/page-1.png\n"],
)
def test_knowledge_chunk_rejects_unsafe_image_reference(image_ref: str) -> None:
    with pytest.raises(ValueError, match="image_refs"):
        replace(_chunk(), image_refs=(image_ref,))
