from __future__ import annotations

import asyncio

from saxophone.tagging.models import ContentRole, ParagraphConceptRole
from saxophone.tagging.sqlite_repository import SqliteTaggingRepository


def test_sqlite_repository_round_trips_relations_deterministically(tmp_path) -> None:
    repository = SqliteTaggingRepository(tmp_path / "tagging.sqlite3")
    relations = (
        ParagraphConceptRole("chunk:p2", "Harmony", ContentRole.DEFINITION),
        ParagraphConceptRole("chunk:p1", "Harmony", ContentRole.PROCEDURE),
    )

    asyncio.run(repository.replace_relations("doc-1", "v1", relations))

    loaded = asyncio.run(repository.list_relations("doc-1", "v1"))
    assert loaded == (
        ParagraphConceptRole("chunk:p1", "Harmony", ContentRole.PROCEDURE),
        ParagraphConceptRole("chunk:p2", "Harmony", ContentRole.DEFINITION),
    )


def test_sqlite_repository_replaces_one_document_version_atomically(tmp_path) -> None:
    repository = SqliteTaggingRepository(tmp_path / "tagging.sqlite3")
    first = (ParagraphConceptRole("chunk:p1", "Harmony", ContentRole.DEFINITION),)
    second = (ParagraphConceptRole("chunk:p2", "Melody", ContentRole.EXAMPLE),)

    asyncio.run(repository.replace_relations("doc-1", "v1", first))
    asyncio.run(repository.replace_relations("doc-1", "v1", second))

    assert asyncio.run(repository.list_relations("doc-1", "v1")) == second
    assert asyncio.run(repository.list_relations("doc-1", "v2")) == ()


def test_sqlite_repository_rejects_duplicate_relations_before_commit(tmp_path) -> None:
    repository = SqliteTaggingRepository(tmp_path / "tagging.sqlite3")
    relation = ParagraphConceptRole("chunk:p1", "Harmony", ContentRole.DEFINITION)

    try:
        asyncio.run(repository.replace_relations("doc-1", "v1", (relation, relation)))
    except ValueError as error:
        assert str(error) == "relations must be unique"
    else:
        raise AssertionError("expected duplicate relation rejection")

    assert asyncio.run(repository.list_relations("doc-1", "v1")) == ()
