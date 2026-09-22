from __future__ import annotations

import pytest

from saxophone.ingestion.concept_catalog import (
    ConceptCatalogEntry,
    build_concept_catalog,
)
from saxophone.ingestion.models import IngestionSourceChunk
from saxophone.tagging.chunk_models import (
    ChunkParagraphTaggingResult,
    ChunkTaggingLabel,
    ChunkTaggingResult,
)
from saxophone.tagging.chunk_service import ChunkTaggingRun
from saxophone.tagging.concepts import ConceptCandidateExample
from saxophone.tagging.models import ContentRole, ParagraphBlock, ParagraphConceptRole


def _chunk(chunk_id: str, heading: str) -> IngestionSourceChunk:
    return IngestionSourceChunk(
        chunk_id=chunk_id,
        document_ref="doc-1",
        source_version="source-v1",
        search_text=f"Content for {heading}.",
        access_scope="tenant-a",
        metadata={"heading": heading},
    )


def _paragraph(paragraph_id: str, chunk_id: str, ordinal: int, text: str) -> ParagraphBlock:
    return ParagraphBlock(
        paragraph_id=paragraph_id,
        chunk_id=chunk_id,
        ordinal=ordinal,
        text=text,
    )


def _run(
    chunk_id: str,
    labels_by_paragraph: dict[
        str,
        tuple[tuple[str, str, str, tuple[ContentRole, ...]], ...],
    ],
) -> ChunkTaggingRun:
    result_paragraphs = tuple(
        ChunkParagraphTaggingResult(
            paragraph_id,
            tuple(
                ChunkTaggingLabel(
                    generated_concept=generated,
                    action=action,
                    resolved_concept=resolved,
                    roles=roles,
                )
                for generated, action, resolved, roles in labels
            ),
        )
        for paragraph_id, labels in labels_by_paragraph.items()
    )
    result = ChunkTaggingResult(
        chunk_id,
        tuple(
            dict.fromkeys(
                resolved
                for labels in labels_by_paragraph.values()
                for _, action, resolved, _ in labels
                if action != "reuse_existing"
            )
        ),
        result_paragraphs,
    )
    relations = tuple(
        ParagraphConceptRole(paragraph_id, resolved, role)
        for paragraph_id, labels in labels_by_paragraph.items()
        for _, _, resolved, roles in labels
        for role in roles
    )
    return ChunkTaggingRun(result=result, relations=relations)


def test_build_concept_catalog_aggregates_relations_and_orders_examples() -> None:
    chunks = (_chunk("chunk-b", "B section"), _chunk("chunk-a", "A section"))
    paragraphs = (
        _paragraph("chunk-b:p1", "chunk-b", 0, "B paragraph."),
        _paragraph("chunk-a:p2", "chunk-a", 1, "A second paragraph."),
        _paragraph("chunk-a:p1", "chunk-a", 0, "A first paragraph."),
    )
    runs = (
        _run(
            "chunk-b",
            {
                "chunk-b:p1": (
                    (
                        "harmony",
                        "create_new",
                        "Harmony",
                        (ContentRole.DEFINITION, ContentRole.EXAMPLE),
                    ),
                )
            },
        ),
        _run(
            "chunk-a",
            {
                "chunk-a:p2": (
                    ("major triad", "create_new", "Major triad", (ContentRole.PROCEDURE,)),
                ),
                "chunk-a:p1": (
                    ("harmony", "create_new", " harmony ", (ContentRole.DEFINITION,)),
                ),
            },
        ),
    )

    entries = build_concept_catalog(chunks, paragraphs, runs, max_examples=2)

    assert entries == (
        ConceptCatalogEntry(
            canonical_label="Harmony",
            normalized_label="harmony",
            usage_count=2,
            examples=(
                ConceptCandidateExample("A section", "A first paragraph."),
                ConceptCandidateExample("B section", "B paragraph."),
            ),
        ),
        ConceptCatalogEntry(
            canonical_label="Major triad",
            normalized_label="major triad",
            usage_count=1,
            examples=(ConceptCandidateExample("A section", "A second paragraph."),),
        ),
    )


def test_build_concept_catalog_rejects_invalid_run_scope() -> None:
    chunks = (_chunk("chunk-a", "A section"),)
    paragraphs = (_paragraph("chunk-a:p1", "chunk-a", 0, "A paragraph."),)
    run = _run(
        "foreign-chunk",
        {"chunk-a:p1": (("harmony", "create_new", "Harmony", (ContentRole.DEFINITION,)),)},
    )

    with pytest.raises(ValueError, match="chunk"):
        build_concept_catalog(chunks, paragraphs, (run,))


def test_build_concept_catalog_rejects_relation_not_returned_by_result() -> None:
    chunks = (_chunk("chunk-a", "A section"),)
    paragraphs = (_paragraph("chunk-a:p1", "chunk-a", 0, "A paragraph."),)
    run = ChunkTaggingRun(
        result=ChunkTaggingResult(
            "chunk-a",
            ("Harmony",),
            (
                ChunkParagraphTaggingResult(
                    "chunk-a:p1",
                    (
                        ChunkTaggingLabel(
                            "harmony",
                            "create_new",
                            "Harmony",
                            (ContentRole.DEFINITION,),
                        ),
                    ),
                ),
            ),
        ),
        relations=(
            ParagraphConceptRole("chunk-a:p1", "Harmony", ContentRole.PROCEDURE),
        ),
    )

    with pytest.raises(ValueError, match="relations"):
        build_concept_catalog(chunks, paragraphs, (run,))


@pytest.mark.parametrize("max_examples", [0, -1, True])
def test_build_concept_catalog_requires_positive_example_limit(max_examples: int) -> None:
    with pytest.raises(ValueError, match="max_examples"):
        build_concept_catalog((), (), (), max_examples=max_examples)
