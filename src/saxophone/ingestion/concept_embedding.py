"""Prepare bounded, embedded concept-catalog records and outbox events."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from saxophone.documents.policies import is_safe_document_reference
from saxophone.tagging.concepts import ConceptCandidate
from saxophone.tagging.vector_outbox import VectorOutboxEvent

from .concept_catalog import ConceptCatalogEntry
from .concept_records import ConceptVectorRecord, build_concept_vector_record
from .vector_events import build_concept_vector_upsert_events


class ConceptTextEmbeddingProvider(Protocol):
    """Provider boundary for one batch of concept search texts."""

    async def embed_texts(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        ...


@dataclass(frozen=True, slots=True)
class ConceptVectorPreparation:
    """Typed concept records and their transaction-ready outbox events."""

    records: tuple[ConceptVectorRecord, ...]
    events: tuple[VectorOutboxEvent, ...]

    def __post_init__(self) -> None:
        records = tuple(self.records)
        events = tuple(self.events)
        if any(not isinstance(record, ConceptVectorRecord) for record in records):
            raise ValueError("records must contain ConceptVectorRecord values")
        if any(not isinstance(event, VectorOutboxEvent) for event in events):
            raise ValueError("events must contain VectorOutboxEvent values")
        if len({record.normalized_label for record in records}) != len(records):
            raise ValueError("records must have unique normalized labels")
        if len({event.event_id for event in events}) != len(events):
            raise ValueError("events must have unique event IDs")
        if any(event.collection != "concept_catalog" for event in events):
            raise ValueError("events must target concept_catalog")
        if {event.record_id for event in events} != {record.record_id for record in records}:
            raise ValueError("events must cover exactly the prepared records")
        object.__setattr__(self, "records", records)
        object.__setattr__(self, "events", events)


class ConceptCatalogVectorPreparationService:
    """Embed a bounded global catalog projection without performing persistence."""

    def __init__(
        self,
        provider: ConceptTextEmbeddingProvider,
        *,
        max_examples: int = 3,
    ) -> None:
        if not callable(getattr(provider, "embed_texts", None)):
            raise TypeError("provider must provide embed_texts")
        if (
            isinstance(max_examples, bool)
            or not isinstance(max_examples, int)
            or max_examples < 1
        ):
            raise ValueError("max_examples must be a positive integer")
        self._provider = provider
        self._max_examples = max_examples

    async def prepare(
        self,
        entries: Sequence[ConceptCatalogEntry],
        *,
        embedding_model: str,
        catalog_ref: str,
        catalog_version: str,
        index_version: str,
        ingestion_run_id: str | None = None,
    ) -> ConceptVectorPreparation:
        """Build records and events from a validated, deterministic catalog view."""

        normalized_entries = self._validate_inputs(
            entries,
            embedding_model=embedding_model,
            catalog_ref=catalog_ref,
            catalog_version=catalog_version,
            index_version=index_version,
            ingestion_run_id=ingestion_run_id,
        )
        if not normalized_entries:
            return ConceptVectorPreparation((), ())

        candidates = tuple(
            _candidate_from_entry(entry) for entry in normalized_entries
        )
        search_texts = tuple(
            _concept_search_text(candidate, max_examples=self._max_examples)
            for candidate in candidates
        )
        embeddings = await self._provider.embed_texts(search_texts)
        normalized_embeddings = _validate_embeddings(embeddings, len(search_texts))
        records = tuple(
            build_concept_vector_record(
                candidate,
                embedding=embedding,
                embedding_model=embedding_model,
                index_version=index_version,
                max_examples=self._max_examples,
            )
            for candidate, embedding in zip(candidates, normalized_embeddings)
        )
        events = build_concept_vector_upsert_events(
            records,
            catalog_ref=catalog_ref,
            catalog_version=catalog_version,
            index_version=index_version,
            ingestion_run_id=ingestion_run_id,
        )
        return ConceptVectorPreparation(records, events)

    @staticmethod
    def _validate_inputs(
        entries: Sequence[ConceptCatalogEntry],
        *,
        embedding_model: str,
        catalog_ref: str,
        catalog_version: str,
        index_version: str,
        ingestion_run_id: str | None,
    ) -> tuple[ConceptCatalogEntry, ...]:
        if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
            raise ValueError("entries must be a sequence")
        normalized = tuple(entries)
        if any(not isinstance(entry, ConceptCatalogEntry) for entry in normalized):
            raise ValueError("entries must contain ConceptCatalogEntry values")
        normalized = tuple(sorted(normalized, key=lambda entry: entry.normalized_label))
        labels = tuple(entry.normalized_label for entry in normalized)
        if len(labels) != len(set(labels)):
            raise ValueError("entries must have unique normalized labels")
        _require_non_blank("embedding_model", embedding_model)
        _require_non_blank("catalog_ref", catalog_ref)
        if not is_safe_document_reference(catalog_ref.strip()):
            raise ValueError("catalog_ref must be a safe document reference")
        _require_non_blank("catalog_version", catalog_version)
        _require_non_blank("index_version", index_version)
        if ingestion_run_id is not None and (
            not isinstance(ingestion_run_id, str) or not ingestion_run_id.strip()
        ):
            raise ValueError("ingestion_run_id must be blank or null")
        return normalized


def _candidate_from_entry(entry: ConceptCatalogEntry) -> ConceptCandidate:
    """Adapt catalog facts to the shared deterministic vector projection."""

    return ConceptCandidate(
        canonical_label=entry.canonical_label,
        rank=1,
        semantic_score=0.0,
        usage_count=entry.usage_count,
        examples=entry.examples,
    )


def _concept_search_text(candidate: ConceptCandidate, *, max_examples: int) -> str:
    examples = candidate.examples[:max_examples]
    return "\n".join(
        [
            candidate.canonical_label,
            *(f"{example.header}: {example.excerpt}" for example in examples),
        ]
    )


def _validate_embeddings(
    embeddings: Sequence[Sequence[float]], expected_count: int
) -> tuple[tuple[float, ...], ...]:
    if isinstance(embeddings, (str, bytes)) or not isinstance(embeddings, Sequence):
        raise ValueError("embedding result must be a sequence")
    if len(embeddings) != expected_count:
        raise ValueError("embedding count does not match concept count")
    normalized: list[tuple[float, ...]] = []
    for embedding in embeddings:
        if isinstance(embedding, (str, bytes)) or not isinstance(embedding, Sequence):
            raise ValueError("embedding values must be finite numbers")
        values = tuple(embedding)
        if not values or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in values
        ):
            raise ValueError("embedding values must be finite numbers")
        normalized.append(tuple(float(value) for value in values))
    dimensions = {len(embedding) for embedding in normalized}
    if len(dimensions) > 1:
        raise ValueError("embedding dimensions must match")
    return tuple(normalized)


def _require_non_blank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")
