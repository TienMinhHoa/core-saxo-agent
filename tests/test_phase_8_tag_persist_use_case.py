from __future__ import annotations

import pytest

from saxophone.tagging.models import ParagraphBlock, TaggedParagraph
from saxophone.tagging.use_cases import TagAndPersistParagraph


class _Catalog:
    def __init__(self, tags: tuple[str, ...] = ()) -> None:
        self.tags = tags
        self.added: list[tuple[str, ...]] = []

    async def list(self) -> tuple[str, ...]:
        return self.tags

    async def add(self, tags: tuple[str, ...]) -> None:
        self.added.append(tags)


class _ParagraphRepository:
    def __init__(self) -> None:
        self.saved: list[TaggedParagraph] = []

    async def upsert(self, paragraph: TaggedParagraph) -> None:
        self.saved.append(paragraph)


class _Tagger:
    def __init__(self) -> None:
        self.candidates: tuple[str, ...] = ()

    async def execute(self, paragraph, *, tagging_profile, resolution_profile, existing_tags=()):
        self.candidates = tuple(candidate.tag for candidate in existing_tags)
        return TaggedParagraph(
            paragraph_id=paragraph.paragraph_id,
            text=paragraph.text,
            generated_tags=("Concept of harmony",),
            tags=("Harmony definition",),
            status="completed",
        )


def _paragraph() -> ParagraphBlock:
    return ParagraphBlock(
        paragraph_id="chunk-1:p0000",
        chunk_id="chunk-1",
        ordinal=0,
        text="Harmony source",
    )


@pytest.mark.anyio
async def test_tag_and_persist_loads_candidates_and_persists_catalog_and_sidecar() -> None:
    catalog = _Catalog(("Harmony definition",))
    repository = _ParagraphRepository()
    tagger = _Tagger()

    result = await TagAndPersistParagraph(tagger, repository, catalog).execute(
        _paragraph(), tagging_profile="topic-v1", resolution_profile="resolve-v1"
    )

    assert result.status == "completed"
    assert tagger.candidates == ("Harmony definition",)
    assert repository.saved == [result]
    assert catalog.added == [("Harmony definition",)]


@pytest.mark.anyio
async def test_tag_and_persist_does_not_hide_persistence_failure() -> None:
    class _FailingRepository(_ParagraphRepository):
        async def upsert(self, paragraph: TaggedParagraph) -> None:
            raise OSError("sidecar unavailable")

    with pytest.raises(OSError, match="sidecar unavailable"):
        await TagAndPersistParagraph(_Tagger(), _FailingRepository(), _Catalog()).execute(
            _paragraph(), tagging_profile="topic-v1", resolution_profile="resolve-v1"
        )
