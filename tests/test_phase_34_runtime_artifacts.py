import json

import pytest

from saxophone.ingestion.models import IngestionReport
from saxophone.tagging.artifacts import TopicTaggingArtifactExporter
from saxophone.tagging.models import ContentRole, ParagraphConceptRole, TaggedParagraph


def _report() -> IngestionReport:
    return IngestionReport(
        document_ref="harmony.md",
        source_version="v1",
        chunk_count=1,
        paragraph_count=2,
        tagged_paragraph_count=2,
        failed_paragraph_count=0,
        embedded_count=1,
        reused_embedding_count=0,
        skipped_count=0,
        index_version="chunks-v1",
        indexed=True,
        warnings=(),
        errors=(),
    )


def _paragraphs() -> tuple[TaggedParagraph, ...]:
    return (
        TaggedParagraph(
            paragraph_id="chunk-1:p2",
            chunk_id="chunk-1",
            ordinal=2,
            text="A chord has three notes.",
            generated_tags=("Chord",),
            tags=("Chord",),
            status="completed",
        ),
        TaggedParagraph(
            paragraph_id="chunk-1:p1",
            chunk_id="chunk-1",
            ordinal=1,
            text="Harmony combines notes.",
            generated_tags=("Harmony",),
            tags=("Harmony",),
            status="completed",
        ),
    )


def test_exports_all_required_artifacts_deterministically(tmp_path):
    exporter = TopicTaggingArtifactExporter(tmp_path)
    exporter.export(
        document_ref="harmony.md",
        source_version="v1",
        paragraphs=_paragraphs(),
        relations=(
            ParagraphConceptRole("chunk-1:p1", "Harmony", ContentRole.DEFINITION),
            ParagraphConceptRole("chunk-1:p2", "Chord", ContentRole.EXAMPLE),
        ),
        ingestion_report=_report(),
    )

    expected = {
        "document-tagged-chunks.json",
        "concept-catalog.json",
        "tagging-run.json",
        "ingestion-run.json",
        "document-tagged-review.md",
    }
    assert {path.name for path in tmp_path.iterdir()} == expected

    chunks = json.loads((tmp_path / "document-tagged-chunks.json").read_text(encoding="utf-8"))
    assert chunks["chunks"][0]["paragraphs"][0]["paragraph_id"] == "chunk-1:p1"
    assert json.loads((tmp_path / "concept-catalog.json").read_text(encoding="utf-8")) == [
        "Chord",
        "Harmony",
    ]
    tagging_run = json.loads((tmp_path / "tagging-run.json").read_text(encoding="utf-8"))
    assert tagging_run == {
        "chunk_count": 1,
            "document_ref": "harmony.md",
        "failed_paragraph_count": 0,
        "paragraph_count": 2,
        "relation_count": 2,
        "source_version": "v1",
        "tagged_paragraph_count": 2,
    }
    assert "# Topic tagging review" in (tmp_path / "document-tagged-review.md").read_text(encoding="utf-8")


def test_rejects_foreign_relations_and_report_identity_mismatches(tmp_path):
    exporter = TopicTaggingArtifactExporter(tmp_path)

    with pytest.raises(ValueError, match="known tagged paragraph"):
        exporter.export(
            document_ref="harmony.md",
            source_version="v1",
            paragraphs=_paragraphs(),
            relations=(ParagraphConceptRole("foreign", "Harmony", ContentRole.DEFINITION),),
            ingestion_report=_report(),
        )

    with pytest.raises(ValueError, match="ingestion_report source_version"):
        exporter.export(
            document_ref="harmony.md",
            source_version="v2",
            paragraphs=_paragraphs(),
            relations=(),
            ingestion_report=_report(),
        )
