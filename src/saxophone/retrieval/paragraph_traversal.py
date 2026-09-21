"""Resolve selected concept-role pairs back to source paragraphs."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from saxophone.tagging.concepts import normalize_concept_label
from saxophone.tagging.models import ParagraphConceptRole

from .renderers import AnswerContextModel, SelectedConceptRole, SourceParagraph


@dataclass(frozen=True, slots=True)
class ParagraphTraversal:
    """Traverse source-of-truth relations inside the selected chunk boundary."""

    def resolve(
        self,
        selections: tuple[SelectedConceptRole, ...],
        relations: tuple[ParagraphConceptRole, ...],
        paragraphs: Mapping[str, SourceParagraph],
    ) -> AnswerContextModel:
        if any(not isinstance(item, SelectedConceptRole) for item in selections):
            raise ValueError("selections must contain SelectedConceptRole values")
        if any(not isinstance(item, ParagraphConceptRole) for item in relations):
            raise ValueError("relations must contain ParagraphConceptRole values")

        relation_keys: set[tuple[str, str, str]] = set()
        relation_rows: list[tuple[str, str, str]] = []
        for relation in relations:
            key = (
                relation.paragraph_id,
                normalize_concept_label(relation.canonical_concept),
                relation.content_role.value,
            )
            if key in relation_keys:
                raise ValueError("relations must not contain duplicate entries")
            relation_keys.add(key)
            paragraph = paragraphs.get(relation.paragraph_id)
            if paragraph is None:
                raise ValueError("relation references a missing paragraph")
            relation_rows.append(key)

        resolved: list[SelectedConceptRole] = []
        paragraph_registry: dict[str, SourceParagraph] = {}
        for selection in selections:
            allowed_chunks = {chunk.chunk_id for chunk in selection.parent_chunks}
            refs = sorted(
                paragraph_ref
                for paragraph_ref, concept, role in relation_rows
                if concept == normalize_concept_label(selection.concept)
                and role == selection.role
                and _chunk_id(paragraphs[paragraph_ref]) in allowed_chunks
            )
            if not refs:
                raise ValueError("selected concept-role pair has no paragraph")
            for paragraph_ref in refs:
                paragraph_registry.setdefault(paragraph_ref, paragraphs[paragraph_ref])
            resolved.append(
                SelectedConceptRole(
                    selection.concept,
                    selection.role,
                    tuple(refs),
                    selection.parent_chunks,
                )
            )
        return AnswerContextModel(tuple(resolved), tuple(paragraph_registry.values()))


def _chunk_id(paragraph: SourceParagraph) -> str:
    """Prefer the explicit stable chunk id; retain legacy DTO compatibility."""

    return paragraph.chunk_id or paragraph.parent_header
