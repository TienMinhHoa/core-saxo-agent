"""Deterministic Markdown renderers for retrieval model prompts."""

from __future__ import annotations

from dataclasses import dataclass

from saxophone.tagging.concepts import normalize_concept_label
from saxophone.tagging.models import ParagraphConceptRole


@dataclass(frozen=True, slots=True)
class RoleAvailability:
    role: str
    paragraph_count: int


@dataclass(frozen=True, slots=True)
class ParentChunk:
    chunk_id: str
    rank: int


@dataclass(frozen=True, slots=True)
class ConceptInventoryItem:
    concept: str
    available_roles: tuple[RoleAvailability, ...]
    parent_chunks: tuple[ParentChunk, ...]


@dataclass(frozen=True, slots=True)
class ConceptInventory:
    concepts: tuple[ConceptInventoryItem, ...]


class ConceptInventoryBuilder:
    """Aggregate source relations into the role-selector inventory DTO."""

    def build(
        self,
        relations: tuple[ParagraphConceptRole, ...],
        *,
        paragraph_chunks: dict[str, str],
        chunk_ranks: dict[str, int],
    ) -> ConceptInventory:
        grouped: dict[str, dict[str, object]] = {}
        seen_relations: set[tuple[str, str, str]] = set()
        for relation in relations:
            if not isinstance(relation, ParagraphConceptRole):
                raise ValueError("relations must contain ParagraphConceptRole values")
            key = (relation.paragraph_id, normalize_concept_label(relation.canonical_concept), relation.content_role.value)
            if key in seen_relations:
                raise ValueError("relations must not contain duplicate entries")
            seen_relations.add(key)
            chunk_id = paragraph_chunks.get(relation.paragraph_id)
            if not isinstance(chunk_id, str) or not chunk_id.strip():
                raise ValueError("paragraph_chunks must contain every paragraph")
            chunk_id = chunk_id.strip()
            rank = chunk_ranks.get(chunk_id)
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                raise ValueError("chunk rank must be a positive integer")
            concept_key = normalize_concept_label(relation.canonical_concept)
            bucket = grouped.setdefault(
                concept_key,
                {"label": relation.canonical_concept.strip(), "roles": {}, "chunks": {}},
            )
            roles = bucket["roles"]
            chunks = bucket["chunks"]
            assert isinstance(roles, dict) and isinstance(chunks, dict)
            role_paragraphs = roles.setdefault(relation.content_role.value, set())
            assert isinstance(role_paragraphs, set)
            role_paragraphs.add(relation.paragraph_id)
            chunks[chunk_id] = rank

        items: list[ConceptInventoryItem] = []
        for bucket in grouped.values():
            roles = bucket["roles"]
            chunks = bucket["chunks"]
            assert isinstance(roles, dict) and isinstance(chunks, dict)
            items.append(
                ConceptInventoryItem(
                    bucket["label"],
                    tuple(RoleAvailability(role, len(paragraphs)) for role, paragraphs in sorted(roles.items())),
                    tuple(ParentChunk(chunk_id, rank) for chunk_id, rank in sorted(chunks.items(), key=lambda item: (item[1], item[0]))),
                )
            )
        return ConceptInventory(tuple(items))


@dataclass(frozen=True, slots=True)
class SelectedConceptRole:
    concept: str
    role: str
    paragraph_refs: tuple[str, ...]
    parent_chunks: tuple[ParentChunk, ...]


@dataclass(frozen=True, slots=True)
class SourceParagraph:
    paragraph_ref: str
    source: str
    parent_header: str
    nested_headings: tuple[str, ...]
    text: str
    concepts_and_roles: tuple[str, ...]
    pages: tuple[str, ...]
    image_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnswerContextModel:
    selected_roles: tuple[SelectedConceptRole, ...]
    paragraphs: tuple[SourceParagraph, ...]


class RoleSelectionMarkdownRenderer:
    def render_role_selection(self, question: str, inventory: ConceptInventory) -> str:
        lines = ["# Concept and Role Selection", "", "## User question", "", question, "", "## Candidate concepts from retrieved chunks", ""]
        for item in inventory.concepts:
            lines.extend((f"### Concept: {item.concept}", ""))
            lines.extend(f"- Available role: {role.role} — {role.paragraph_count} paragraphs" for role in item.available_roles)
            parents = ", ".join(f"{chunk.chunk_id} (rank {chunk.rank})" for chunk in item.parent_chunks)
            lines.extend((f"- Parent chunks: {parents}", ""))
        return "\n".join(lines)


class AnswerContextMarkdownRenderer:
    def render_answer_context(self, question: str, context: AnswerContextModel) -> str:
        paragraphs = {paragraph.paragraph_ref: paragraph for paragraph in context.paragraphs}
        refs = [ref for selection in context.selected_roles for ref in selection.paragraph_refs]
        if len(refs) != len(set(refs)):
            raise ValueError("paragraph refs must not be duplicated")
        if any(ref not in paragraphs for ref in refs):
            raise ValueError("selected role contains a dangling paragraph ref")
        lines = ["# Retrieval Context", "", "## User question", "", question, "", "## Concept-role map", ""]
        for selection in context.selected_roles:
            refs_text = ", ".join(f"[{ref}]" for ref in selection.paragraph_refs)
            parents = ", ".join(f"{chunk.chunk_id} (rank {chunk.rank})" for chunk in selection.parent_chunks)
            lines.extend((f"### Concept: {selection.concept}", "", f"- Selected role: {selection.role}", f"- Paragraphs: {refs_text}", f"- Parent chunks: {parents}", ""))
        lines.extend(("## Source paragraphs", ""))
        for ref in refs:
            paragraph = paragraphs[ref]
            lines.extend((f"### [{paragraph.paragraph_ref}]", "", f"- Source: {paragraph.source}", f"- Parent header: {paragraph.parent_header}"))
            if paragraph.nested_headings:
                lines.append(f"- Nested heading: {'; '.join(paragraph.nested_headings)}")
            if paragraph.pages:
                lines.append(f"- Pages: {'–'.join(paragraph.pages)}")
            lines.append(f"- Concepts and roles: {'; '.join(paragraph.concepts_and_roles)}")
            lines.append(f"- Images: {', '.join(paragraph.image_refs) if paragraph.image_refs else 'none'}")
            lines.extend(("", paragraph.text, ""))
        return "\n".join(lines)
