from __future__ import annotations

import math

import pytest

from saxophone.ingestion.concept_catalog import ConceptCatalogEntry
from saxophone.ingestion.concept_embedding import (
    ConceptCatalogVectorPreparationService,
)
from saxophone.tagging.concepts import ConceptCandidateExample


def _entry(
    label: str,
    *,
    examples: tuple[ConceptCandidateExample, ...] = (),
    usage_count: int = 1,
) -> ConceptCatalogEntry:
    return ConceptCatalogEntry(
        canonical_label=label,
        normalized_label="",
        usage_count=usage_count,
        examples=examples,
    )


class _RecordingProvider:
    def __init__(self, vectors_by_text: dict[str, tuple[float, ...]]) -> None:
        self.vectors_by_text = vectors_by_text
        self.calls: list[tuple[str, ...]] = []

    async def embed_texts(self, texts):
        normalized = tuple(texts)
        self.calls.append(normalized)
        return tuple(self.vectors_by_text[text] for text in normalized)


@pytest.mark.anyio
async def test_prepares_sorted_concept_records_and_replayable_events() -> None:
    entries = (
        _entry(
            "Beta",
            examples=(ConceptCandidateExample("B", "Beta in context."),),
            usage_count=2,
        ),
        _entry(
            "Alpha",
            examples=(ConceptCandidateExample("A", "Alpha in context."),),
        ),
    )
    alpha_text = "Alpha\nA: Alpha in context."
    beta_text = "Beta\nB: Beta in context."
    provider = _RecordingProvider(
        {alpha_text: (0.1, 0.2), beta_text: (0.3, 0.4)}
    )

    prepared = await ConceptCatalogVectorPreparationService(provider).prepare(
        entries,
        embedding_model="text-embedding-3-small",
        catalog_ref="concept-catalog",
        catalog_version="catalog-v1",
        index_version="concept-v1",
        ingestion_run_id="run-67",
    )

    assert provider.calls == [(alpha_text, beta_text)]
    assert [record.normalized_label for record in prepared.records] == [
        "alpha",
        "beta",
    ]
    assert [record.embedding for record in prepared.records] == [
        (0.1, 0.2),
        (0.3, 0.4),
    ]
    assert [event.record_id for event in prepared.events] == [
        record.record_id for record in prepared.records
    ]
    assert all(event.collection == "concept_catalog" for event in prepared.events)
    assert all(event.ingestion_run_id == "run-67" for event in prepared.events)


@pytest.mark.anyio
async def test_limits_representative_examples_before_embedding() -> None:
    entry = _entry(
        "Harmony",
        examples=(
            ConceptCandidateExample("First", "First excerpt."),
            ConceptCandidateExample("Second", "Second excerpt."),
            ConceptCandidateExample("Third", "Third excerpt."),
        ),
    )
    provider = _RecordingProvider(
        {"Harmony\nFirst: First excerpt.": (0.1, 0.2)}
    )

    await ConceptCatalogVectorPreparationService(provider, max_examples=1).prepare(
        (entry,),
        embedding_model="fake-embedding",
        catalog_ref="concept-catalog",
        catalog_version="catalog-v1",
        index_version="concept-v1",
    )

    assert provider.calls == [("Harmony\nFirst: First excerpt.",)]


@pytest.mark.anyio
async def test_rejects_duplicate_concepts_before_provider_call() -> None:
    provider = _RecordingProvider({})

    with pytest.raises(ValueError, match="unique normalized"):
        await ConceptCatalogVectorPreparationService(provider).prepare(
            (_entry("Harmony"), _entry(" harmony ")),
            embedding_model="fake-embedding",
            catalog_ref="concept-catalog",
            catalog_version="catalog-v1",
            index_version="concept-v1",
        )

    assert provider.calls == []


@pytest.mark.anyio
async def test_rejects_embedding_count_and_dimension_errors() -> None:
    class _BadProvider:
        def __init__(self, result) -> None:
            self.result = result

        async def embed_texts(self, texts):
            return self.result

    entry = _entry("Harmony")
    with pytest.raises(ValueError, match="embedding count"):
        await ConceptCatalogVectorPreparationService(_BadProvider(())).prepare(
            (entry,),
            embedding_model="fake-embedding",
            catalog_ref="concept-catalog",
            catalog_version="catalog-v1",
            index_version="concept-v1",
        )

    with pytest.raises(ValueError, match="dimension"):
        await ConceptCatalogVectorPreparationService(
            _BadProvider(((0.1, 0.2), (0.3,)))
        ).prepare(
            (entry, _entry("Theory")),
            embedding_model="fake-embedding",
            catalog_ref="concept-catalog",
            catalog_version="catalog-v1",
            index_version="concept-v1",
        )

    with pytest.raises(ValueError, match="finite"):
        await ConceptCatalogVectorPreparationService(
            _BadProvider(((math.nan,),))
        ).prepare(
            (entry,),
            embedding_model="fake-embedding",
            catalog_ref="concept-catalog",
            catalog_version="catalog-v1",
            index_version="concept-v1",
        )


@pytest.mark.anyio
async def test_empty_catalog_does_not_call_provider() -> None:
    provider = _RecordingProvider({})

    prepared = await ConceptCatalogVectorPreparationService(provider).prepare(
        (),
        embedding_model="fake-embedding",
        catalog_ref="concept-catalog",
        catalog_version="catalog-v1",
        index_version="concept-v1",
    )

    assert prepared.records == ()
    assert prepared.events == ()
    assert provider.calls == []
