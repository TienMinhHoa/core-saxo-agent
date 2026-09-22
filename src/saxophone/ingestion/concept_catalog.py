"""Deterministic projection of tagged paragraphs into the global concept catalog."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import unicodedata

from saxophone.tagging.chunk_service import ChunkTaggingRun
from saxophone.tagging.concepts import (
    ConceptCandidateExample,
    normalize_concept_label,
)
from saxophone.tagging.chunk_models import ChunkTaggingResult
from saxophone.tagging.models import ParagraphBlock, ParagraphConceptRole

from .models import IngestionSourceChunk


@dataclass(frozen=True, slots=True)
class ConceptCatalogEntry:
    """One canonical concept with bounded representative source examples."""

    canonical_label: str
    normalized_label: str
    usage_count: int
    examples: tuple[ConceptCandidateExample, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_label, str) or not self.canonical_label.strip():
            raise ValueError("canonical_label must not be blank")
        canonical = unicodedata.normalize("NFC", " ".join(self.canonical_label.split()))
        expected_normalized = normalize_concept_label(canonical)
        if self.normalized_label and self.normalized_label != expected_normalized:
            raise ValueError("normalized_label does not match canonical_label")
        if (
            isinstance(self.usage_count, bool)
            or not isinstance(self.usage_count, int)
            or self.usage_count < 1
        ):
            raise ValueError("usage_count must be a positive integer")
        if isinstance(self.examples, (str, bytes)) or not isinstance(self.examples, Sequence):
            raise ValueError("examples must be a sequence of ConceptCandidateExample values")
        normalized_examples = tuple(self.examples)
        if any(not isinstance(item, ConceptCandidateExample) for item in normalized_examples):
            raise ValueError("examples must contain ConceptCandidateExample values")
        example_keys = tuple((item.header, item.excerpt) for item in normalized_examples)
        if len(example_keys) != len(set(example_keys)):
            raise ValueError("examples must not contain duplicates")
        object.__setattr__(self, "canonical_label", canonical)
        object.__setattr__(self, "normalized_label", expected_normalized)
        object.__setattr__(self, "examples", normalized_examples)


def build_concept_catalog(
    chunks: Sequence[IngestionSourceChunk],
    paragraphs: Sequence[ParagraphBlock],
    runs: Sequence[ChunkTaggingRun],
    *,
    max_examples: int = 3,
) -> tuple[ConceptCatalogEntry, ...]:
    """Aggregate validated chunk-tagging relations into global catalog entries.

    Usage counts represent distinct paragraph/concept observations, so multiple
    roles attached to one paragraph do not inflate catalog frequency.
    """

    _validate_positive_limit(max_examples)
    normalized_chunks = _validate_chunks(chunks)
    normalized_paragraphs = _validate_paragraphs(paragraphs, normalized_chunks)
    normalized_runs = _validate_runs(runs, normalized_chunks, normalized_paragraphs)

    paragraphs_by_id = {paragraph.paragraph_id: paragraph for paragraph in normalized_paragraphs}
    chunks_by_id = {chunk.chunk_id: chunk for chunk in normalized_chunks}
    labels_by_key: dict[str, set[str]] = {}
    usage_by_key: dict[str, set[str]] = {}
    examples_by_key: dict[str, dict[str, tuple[str, str, str, int]]] = {}

    for run in normalized_runs:
        for relation in run.relations:
            paragraph = paragraphs_by_id[relation.paragraph_id]
            chunk = chunks_by_id[paragraph.chunk_id]
            normalized_label = normalize_concept_label(relation.canonical_concept)
            labels_by_key.setdefault(normalized_label, set()).add(relation.canonical_concept)
            usage_by_key.setdefault(normalized_label, set()).add(paragraph.paragraph_id)
            examples_by_key.setdefault(normalized_label, {})[paragraph.paragraph_id] = (
                paragraph.chunk_id,
                paragraph.paragraph_id,
                _chunk_header(chunk, paragraph),
                paragraph.ordinal,
            )

    entries: list[ConceptCatalogEntry] = []
    for normalized_label in sorted(labels_by_key):
        canonical_label = min(
            labels_by_key[normalized_label],
            key=lambda value: (value.casefold(), value),
        )
        example_rows = sorted(
            examples_by_key[normalized_label].values(),
            key=lambda value: (value[0], value[3], value[1]),
        )[:max_examples]
        examples = tuple(
            ConceptCandidateExample(header=row[2], excerpt=paragraphs_by_id[row[1]].text)
            for row in example_rows
        )
        entries.append(
            ConceptCatalogEntry(
                canonical_label=canonical_label,
                normalized_label=normalized_label,
                usage_count=len(usage_by_key[normalized_label]),
                examples=examples,
            )
        )
    return tuple(entries)


def _validate_chunks(
    chunks: Sequence[IngestionSourceChunk],
) -> tuple[IngestionSourceChunk, ...]:
    _require_sequence(chunks, "chunks")
    normalized = tuple(chunks)
    if any(not isinstance(item, IngestionSourceChunk) for item in normalized):
        raise ValueError("chunks must contain IngestionSourceChunk values")
    identifiers = tuple(item.chunk_id for item in normalized)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("chunks must have unique chunk IDs")
    return normalized


def _validate_paragraphs(
    paragraphs: Sequence[ParagraphBlock],
    chunks: Sequence[IngestionSourceChunk],
) -> tuple[ParagraphBlock, ...]:
    _require_sequence(paragraphs, "paragraphs")
    normalized = tuple(paragraphs)
    if any(not isinstance(item, ParagraphBlock) for item in normalized):
        raise ValueError("paragraphs must contain ParagraphBlock values")
    identifiers = tuple(item.paragraph_id for item in normalized)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("paragraphs must have unique paragraph IDs")
    chunk_ids = {chunk.chunk_id for chunk in chunks}
    if any(item.chunk_id not in chunk_ids for item in normalized):
        raise ValueError("paragraphs must belong to supplied chunks")
    return normalized


def _validate_runs(
    runs: Sequence[ChunkTaggingRun],
    chunks: Sequence[IngestionSourceChunk],
    paragraphs: Sequence[ParagraphBlock],
) -> tuple[ChunkTaggingRun, ...]:
    _require_sequence(runs, "runs")
    normalized = tuple(runs)
    if any(not isinstance(item, ChunkTaggingRun) for item in normalized):
        raise ValueError("runs must contain ChunkTaggingRun values")
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    paragraphs_by_id = {paragraph.paragraph_id: paragraph for paragraph in paragraphs}
    seen_chunks: set[str] = set()
    for run in normalized:
        if not isinstance(run.result, ChunkTaggingResult):
            raise ValueError("tagging runs must contain ChunkTaggingResult values")
        result = run.result
        if result.chunk_id not in chunks_by_id:
            raise ValueError("tagging run references an unknown chunk")
        if result.chunk_id in seen_chunks:
            raise ValueError("runs must contain one result per chunk")
        seen_chunks.add(result.chunk_id)
        expected_paragraphs = {
            paragraph.paragraph_id
            for paragraph in paragraphs
            if paragraph.chunk_id == result.chunk_id
        }
        result_paragraphs = {item.paragraph_ref for item in result.paragraphs}
        if result_paragraphs != expected_paragraphs:
            raise ValueError("tagging run paragraphs must cover its chunk")
        for paragraph_ref in result_paragraphs:
            if paragraphs_by_id[paragraph_ref].chunk_id != result.chunk_id:
                raise ValueError("tagging run paragraph belongs to a different chunk")
        _validate_run_relations(run, result_paragraphs)
    return normalized


def _validate_run_relations(run: ChunkTaggingRun, paragraph_refs: set[str]) -> None:
    if any(not isinstance(relation, ParagraphConceptRole) for relation in run.relations):
        raise ValueError("relations must contain ParagraphConceptRole values")
    expected = {
        (paragraph.paragraph_ref, label.resolved_concept, role)
        for paragraph in run.result.paragraphs
        for label in paragraph.labels
        for role in label.roles
    }
    actual = tuple(
        (relation.paragraph_id, relation.canonical_concept, relation.content_role)
        for relation in run.relations
    )
    if any(relation.paragraph_id not in paragraph_refs for relation in run.relations):
        raise ValueError("relations must belong to the tagging run paragraphs")
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("relations must match the tagging result")


def _chunk_header(chunk: IngestionSourceChunk, paragraph: ParagraphBlock) -> str:
    for key in ("header", "heading"):
        value = chunk.metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    heading_path = chunk.metadata.get("heading_path")
    if isinstance(heading_path, Sequence) and not isinstance(heading_path, (str, bytes)):
        values = tuple(value.strip() for value in heading_path if isinstance(value, str) and value.strip())
        if values:
            return " > ".join(values)
    if paragraph.heading_path:
        return " > ".join(paragraph.heading_path)
    return chunk.chunk_id


def _validate_positive_limit(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("max_examples must be a positive integer")


def _require_sequence(value: object, name: str) -> None:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence")
