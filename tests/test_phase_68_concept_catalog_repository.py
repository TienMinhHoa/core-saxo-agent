from __future__ import annotations

import pytest

from saxophone.ingestion.concept_catalog import ConceptCatalogEntry
from saxophone.ingestion.concept_repository import SqliteConceptCatalogRepository
from saxophone.tagging.concepts import ConceptCandidateExample


def _entry(
    label: str,
    *,
    usage_count: int = 1,
    examples: tuple[ConceptCandidateExample, ...] = (),
) -> ConceptCatalogEntry:
    return ConceptCatalogEntry(
        canonical_label=label,
        normalized_label="",
        usage_count=usage_count,
        examples=examples,
    )


@pytest.mark.anyio
async def test_replaces_source_observations_and_rebuilds_global_catalog(tmp_path) -> None:
    repository = SqliteConceptCatalogRepository(tmp_path / "catalog.sqlite3")

    await repository.replace_document_entries(
        "doc-b",
        "source-v1",
        (
            _entry(
                "Harmony",
                usage_count=1,
                examples=(ConceptCandidateExample("B", "B excerpt."),),
            ),
        ),
    )
    await repository.replace_document_entries(
        "doc-a",
        "source-v1",
        (
            _entry(
                " harmony ",
                usage_count=2,
                examples=(ConceptCandidateExample("A", "A excerpt."),),
            ),
            _entry("Theory", usage_count=1),
        ),
    )

    assert await repository.list_entries() == (
        ConceptCatalogEntry(
            canonical_label="Harmony",
            normalized_label="harmony",
            usage_count=3,
            examples=(
                ConceptCandidateExample("A", "A excerpt."),
                ConceptCandidateExample("B", "B excerpt."),
            ),
        ),
        ConceptCatalogEntry(
            canonical_label="Theory",
            normalized_label="theory",
            usage_count=1,
            examples=(),
        ),
    )


@pytest.mark.anyio
async def test_reingestion_replaces_prior_source_version_without_double_counting(
    tmp_path,
) -> None:
    repository = SqliteConceptCatalogRepository(tmp_path / "catalog.sqlite3")

    await repository.replace_document_entries(
        "doc-a",
        "source-v1",
        (_entry("Harmony", usage_count=3), _entry("Legacy", usage_count=1)),
    )
    await repository.replace_document_entries(
        "doc-a",
        "source-v2",
        (_entry("Harmony", usage_count=1), _entry("Theory", usage_count=2)),
        previous_source_versions=("source-v1",),
    )

    assert await repository.list_entries() == (
        ConceptCatalogEntry(
            canonical_label="Harmony",
            normalized_label="harmony",
            usage_count=1,
            examples=(),
        ),
        ConceptCatalogEntry(
            canonical_label="Theory",
            normalized_label="theory",
            usage_count=2,
            examples=(),
        ),
    )


@pytest.mark.anyio
async def test_replaying_same_source_version_is_idempotent(tmp_path) -> None:
    repository = SqliteConceptCatalogRepository(tmp_path / "catalog.sqlite3")
    entries = (_entry("Harmony", usage_count=2),)

    first = await repository.replace_document_entries("doc-a", "source-v1", entries)
    second = await repository.replace_document_entries("doc-a", "source-v1", entries)

    assert first == second == entries


@pytest.mark.anyio
async def test_invalid_replacement_does_not_mutate_existing_catalog(tmp_path) -> None:
    repository = SqliteConceptCatalogRepository(tmp_path / "catalog.sqlite3")
    existing = (_entry("Harmony", usage_count=2),)
    await repository.replace_document_entries("doc-a", "source-v1", existing)

    with pytest.raises(ValueError, match="unique normalized"):
        await repository.replace_document_entries(
            "doc-a",
            "source-v2",
            (_entry("Harmony"), _entry(" harmony ")),
        )

    assert await repository.list_entries() == existing


@pytest.mark.anyio
async def test_rejects_current_source_version_in_previous_scope(tmp_path) -> None:
    repository = SqliteConceptCatalogRepository(tmp_path / "catalog.sqlite3")

    with pytest.raises(ValueError, match="must not contain the new source version"):
        await repository.replace_document_entries(
            "doc-a",
            "source-v1",
            (),
            previous_source_versions=("source-v1",),
        )
