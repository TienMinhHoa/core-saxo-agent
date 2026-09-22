"""Deterministic, source-preserving runtime artifacts for topic-tagging runs."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from saxophone.ingestion.models import IngestionReport

from .models import ParagraphConceptRole, TaggedParagraph


class TopicTaggingArtifactExporter:
    """Write the five review artifacts required for one completed document run."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise ValueError("root must be a Path")
        if root.exists() and not root.is_dir():
            raise ValueError("root must be a directory")
        self._root = root.absolute()

    def export(
        self,
        *,
        document_ref: str,
        source_version: str,
        paragraphs: tuple[TaggedParagraph, ...],
        relations: tuple[ParagraphConceptRole, ...],
        ingestion_report: IngestionReport,
    ) -> None:
        _require_non_blank("document_ref", document_ref)
        _require_non_blank("source_version", source_version)
        if not isinstance(ingestion_report, IngestionReport):
            raise ValueError("ingestion_report must be an IngestionReport")
        if ingestion_report.document_ref != document_ref:
            raise ValueError("ingestion_report document_ref does not match export")
        if ingestion_report.source_version != source_version:
            raise ValueError("ingestion_report source_version does not match export")
        if any(not isinstance(paragraph, TaggedParagraph) for paragraph in paragraphs):
            raise ValueError("paragraphs must contain TaggedParagraph values")
        if any(not isinstance(relation, ParagraphConceptRole) for relation in relations):
            raise ValueError("relations must contain ParagraphConceptRole values")

        ordered_paragraphs = tuple(sorted(paragraphs, key=_paragraph_sort_key))
        paragraph_refs = tuple(paragraph.paragraph_id for paragraph in ordered_paragraphs)
        if len(set(paragraph_refs)) != len(paragraph_refs):
            raise ValueError("paragraphs must not contain duplicate paragraph IDs")
        known_refs = set(paragraph_refs)
        if any(relation.paragraph_id not in known_refs for relation in relations):
            raise ValueError("relations must reference a known tagged paragraph")

        ordered_relations = tuple(
            sorted(
                relations,
                key=lambda relation: (
                    relation.canonical_concept.casefold(),
                    relation.canonical_concept,
                    relation.content_role.value,
                    relation.paragraph_id,
                ),
            )
        )
        if len(set(ordered_relations)) != len(ordered_relations):
            raise ValueError("relations must not contain duplicates")

        self._root.mkdir(parents=True, exist_ok=True)
        _write_json(self._root / "document-tagged-chunks.json", _chunk_payload(document_ref, source_version, ordered_paragraphs))
        _write_json(
            self._root / "concept-catalog.json",
            sorted({relation.canonical_concept for relation in ordered_relations}, key=lambda concept: (concept.casefold(), concept)),
        )
        _write_json(
            self._root / "tagging-run.json",
            {
                "document_ref": document_ref,
                "source_version": source_version,
                "chunk_count": len({paragraph.chunk_id for paragraph in ordered_paragraphs}),
                "paragraph_count": len(ordered_paragraphs),
                "tagged_paragraph_count": sum(paragraph.status == "completed" for paragraph in ordered_paragraphs),
                "failed_paragraph_count": sum(paragraph.status == "failed" for paragraph in ordered_paragraphs),
                "relation_count": len(ordered_relations),
            },
        )
        _write_json(self._root / "ingestion-run.json", _report_payload(ingestion_report))
        _write_text(self._root / "document-tagged-review.md", _review_markdown(document_ref, source_version, ordered_paragraphs, ordered_relations))


def _chunk_payload(
    document_ref: str,
    source_version: str,
    paragraphs: tuple[TaggedParagraph, ...],
) -> dict[str, object]:
    chunks: dict[str, list[dict[str, object]]] = {}
    for paragraph in paragraphs:
        chunks.setdefault(paragraph.chunk_id, []).append(
            {
                "paragraph_id": paragraph.paragraph_id,
                "ordinal": paragraph.ordinal,
                "text": paragraph.text,
                "generated_tags": list(paragraph.generated_tags),
                "tags": list(paragraph.tags),
                "status": paragraph.status,
                "heading_path": list(paragraph.heading_path),
                "image_refs": list(paragraph.image_refs),
                "image_captions": dict(paragraph.image_captions),
                "exact_content_hash": paragraph.exact_content_hash,
                "normalized_identity_hash": paragraph.normalized_identity_hash,
            }
        )
    return {
        "document_ref": document_ref,
        "source_version": source_version,
        "chunks": [
            {"chunk_id": chunk_id, "paragraphs": chunks[chunk_id]}
            for chunk_id in sorted(chunks)
        ],
    }


def _report_payload(report: IngestionReport) -> dict[str, object]:
    return {
        "document_ref": report.document_ref,
        "source_version": report.source_version,
        "chunk_count": report.chunk_count,
        "paragraph_count": report.paragraph_count,
        "tagged_paragraph_count": report.tagged_paragraph_count,
        "failed_paragraph_count": report.failed_paragraph_count,
        "embedded_count": report.embedded_count,
        "reused_embedding_count": report.reused_embedding_count,
        "skipped_count": report.skipped_count,
        "index_version": report.index_version,
        "indexed": report.indexed,
        "warnings": list(report.warnings),
        "errors": list(report.errors),
    }


def _review_markdown(
    document_ref: str,
    source_version: str,
    paragraphs: tuple[TaggedParagraph, ...],
    relations: tuple[ParagraphConceptRole, ...],
) -> str:
    relations_by_paragraph: dict[str, list[ParagraphConceptRole]] = {}
    for relation in relations:
        relations_by_paragraph.setdefault(relation.paragraph_id, []).append(relation)
    lines = ["# Topic tagging review", "", f"Document: `{document_ref}`", f"Source version: `{source_version}`", ""]
    for paragraph in paragraphs:
        lines.extend((f"## {paragraph.paragraph_id}", "", paragraph.text, "", f"Status: {paragraph.status}", f"Tags: {', '.join(paragraph.tags) or '(none)'}"))
        paragraph_relations = relations_by_paragraph.get(paragraph.paragraph_id, ())
        if paragraph_relations:
            lines.append("Concept roles:")
            lines.extend(f"- {item.canonical_concept}: {item.content_role.value}" for item in paragraph_relations)
        lines.append("")
    return "\n".join(lines)


def _paragraph_sort_key(paragraph: TaggedParagraph) -> tuple[str, int, str]:
    return paragraph.chunk_id, paragraph.ordinal, paragraph.paragraph_id


def _write_json(path: Path, payload: object) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write_text(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _require_non_blank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")
