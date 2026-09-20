from __future__ import annotations

import asyncio

import pytest

from saxophone.tagging.models import TaggedParagraph
from saxophone.tagging.ports import TagCatalogRepository, TaggedParagraphRepository


class _TaggedParagraphStore:
    def __init__(self) -> None:
        self._items: dict[str, TaggedParagraph] = {}

    async def upsert(self, paragraph: TaggedParagraph) -> None:
        self._items[paragraph.paragraph_id] = paragraph

    async def get(self, paragraph_id: str) -> TaggedParagraph:
        try:
            return self._items[paragraph_id]
        except KeyError as error:
            raise FileNotFoundError(paragraph_id) from error

    async def delete(self, paragraph_id: str) -> None:
        try:
            del self._items[paragraph_id]
        except KeyError as error:
            raise FileNotFoundError(paragraph_id) from error


class _TagCatalog:
    def __init__(self) -> None:
        self._tags: set[str] = set()

    async def add(self, tags: tuple[str, ...]) -> None:
        self._tags.update(tags)

    async def list(self) -> tuple[str, ...]:
        return tuple(sorted(self._tags))


def _paragraph(*, text: str = "Harmony source") -> TaggedParagraph:
    return TaggedParagraph(
        paragraph_id="chunk-1:p0000",
        text=text,
        generated_tags=("Concept of harmony",),
        tags=("Harmony definition",),
        status="completed",
    )


def test_tagged_paragraph_repository_is_source_preserving_and_replaceable() -> None:
    repository: TaggedParagraphRepository = _TaggedParagraphStore()
    original = _paragraph()
    replacement = _paragraph(text="Updated harmony source")

    asyncio.run(repository.upsert(original))
    assert asyncio.run(repository.get(original.paragraph_id)) == original
    asyncio.run(repository.upsert(replacement))
    assert asyncio.run(repository.get(original.paragraph_id)).text == "Updated harmony source"


def test_tagged_paragraph_repository_reports_missing_records() -> None:
    repository: TaggedParagraphRepository = _TaggedParagraphStore()

    with pytest.raises(FileNotFoundError):
        asyncio.run(repository.get("missing"))
    with pytest.raises(FileNotFoundError):
        asyncio.run(repository.delete("missing"))


def test_tag_catalog_is_deterministic_and_deduplicated() -> None:
    catalog: TagCatalogRepository = _TagCatalog()

    asyncio.run(catalog.add(("Harmony definition", "Chord construction")))
    asyncio.run(catalog.add(("Harmony definition",)))

    assert asyncio.run(catalog.list()) == ("Chord construction", "Harmony definition")
