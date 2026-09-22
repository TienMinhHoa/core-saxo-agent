"""SQLite hydration for concept-role retrieval context."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from saxophone.tagging.models import ParagraphConceptRole

from .models import ChunkHit
from .renderers import SourceParagraph


@dataclass(frozen=True, slots=True)
class RetrievalContext:
    relations: tuple[ParagraphConceptRole, ...]
    paragraphs: Mapping[str, SourceParagraph]

    def __post_init__(self) -> None:
        if any(not isinstance(item, ParagraphConceptRole) for item in self.relations):
            raise ValueError("relations must contain ParagraphConceptRole values")
        if not isinstance(self.paragraphs, Mapping):
            raise ValueError("paragraphs must be a mapping")
        if any(
            not isinstance(ref, str)
            or not ref.strip()
            or not isinstance(paragraph, SourceParagraph)
            or paragraph.paragraph_ref != ref
            for ref, paragraph in self.paragraphs.items()
        ):
            raise ValueError("paragraphs must contain matching SourceParagraph values")
        object.__setattr__(self, "relations", tuple(self.relations))
        object.__setattr__(self, "paragraphs", MappingProxyType(dict(self.paragraphs)))


class SqliteRetrievalContextRepository:
    """Hydrate source paragraphs and concept-role facts for ranked chunk hits."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path) or path.name in {"", ".", ".."}:
            raise ValueError("path must name a SQLite database file")
        if path.exists() and path.is_dir():
            raise ValueError("path must be a file")
        self._path = path.absolute()

    async def load_for_hits(self, hits: Sequence[ChunkHit]) -> RetrievalContext:
        if isinstance(hits, (str, bytes)) or not isinstance(hits, Sequence):
            raise ValueError("hits must be a sequence")
        normalized = tuple(hits)
        if any(not isinstance(hit, ChunkHit) for hit in normalized):
            raise ValueError("hits must contain ChunkHit values")
        scopes = tuple(_hit_scope(hit) for hit in normalized)
        if len(scopes) != len(set(scopes)):
            raise ValueError("hits must not repeat a chunk scope")
        return await asyncio.to_thread(self._load, scopes)

    def _load(
        self,
        scopes: tuple[tuple[str, str, str], ...],
    ) -> RetrievalContext:
        if not scopes:
            return RetrievalContext((), {})
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            paragraph_rows: list[tuple[object, ...]] = []
            relation_rows: list[tuple[str, str, str]] = []
            for document_ref, source_version, chunk_id in scopes:
                paragraph_rows.extend(
                    connection.execute(
                        """
                        SELECT p.paragraph_id, p.chunk_id, p.order_index, p.text,
                               p.heading_path_json, p.image_refs_json,
                               c.metadata_json, c.document_ref
                        FROM source_paragraphs p
                        JOIN source_chunks c
                          ON c.document_ref = p.document_ref
                         AND c.source_version = p.source_version
                         AND c.chunk_id = p.chunk_id
                        WHERE p.document_ref = ? AND p.source_version = ?
                          AND p.chunk_id = ?
                        ORDER BY p.order_index, p.paragraph_id
                        """,
                        (document_ref, source_version, chunk_id),
                    ).fetchall()
                )
                relation_rows.extend(
                    connection.execute(
                        """
                        SELECT r.paragraph_id, r.canonical_concept, r.content_role
                        FROM paragraph_concept_roles r
                        JOIN source_paragraphs p
                          ON p.document_ref = r.document_ref
                         AND p.source_version = r.source_version
                         AND p.paragraph_id = r.paragraph_id
                        WHERE r.document_ref = ? AND r.source_version = ?
                          AND p.chunk_id = ?
                        ORDER BY r.paragraph_id, r.canonical_concept, r.content_role
                        """,
                        (document_ref, source_version, chunk_id),
                    ).fetchall()
                )

        relations = tuple(
            ParagraphConceptRole(paragraph_ref, concept, role)
            for paragraph_ref, concept, role in relation_rows
        )
        relation_labels: dict[str, list[str]] = {}
        for relation in relations:
            relation_labels.setdefault(relation.paragraph_id, []).append(
                f"{relation.canonical_concept} -> {relation.content_role.value}"
            )
        paragraphs: dict[str, SourceParagraph] = {}
        for row in paragraph_rows:
            paragraph_ref, chunk_id, _, text, headings_json, images_json, metadata_json, document_ref = row
            metadata = _json_mapping(metadata_json, "chunk metadata")
            headings = _json_strings(headings_json, "paragraph headings")
            images = _json_strings(images_json, "paragraph images")
            source = _metadata_text(metadata, "source", fallback=document_ref)
            parent_header = _metadata_text(
                metadata,
                "header",
                fallback=_metadata_text(metadata, "heading", fallback=chunk_id),
            )
            pages = _pages(metadata.get("page_start"), metadata.get("page_end"))
            paragraphs[paragraph_ref] = SourceParagraph(
                paragraph_ref=paragraph_ref,
                source=source,
                parent_header=parent_header,
                nested_headings=headings,
                text=text,
                concepts_and_roles=tuple(relation_labels.get(paragraph_ref, ())),
                pages=pages,
                image_refs=images,
                chunk_id=chunk_id,
            )
        if any(relation.paragraph_id not in paragraphs for relation in relations):
            raise ValueError("stored relation references a missing paragraph")
        return RetrievalContext(relations, paragraphs)

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS source_chunks (
                document_ref TEXT NOT NULL,
                source_version TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                search_text TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                PRIMARY KEY (document_ref, source_version, chunk_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS source_paragraphs (
                document_ref TEXT NOT NULL,
                source_version TEXT NOT NULL,
                paragraph_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                order_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                exact_content_hash TEXT NOT NULL,
                normalized_identity_hash TEXT NOT NULL,
                heading_path_json TEXT NOT NULL,
                image_refs_json TEXT NOT NULL,
                PRIMARY KEY (document_ref, source_version, paragraph_id)
            )
            """
        )


def _hit_scope(hit: ChunkHit) -> tuple[str, str, str]:
    document_ref = hit.metadata.get("document_ref")
    source_version = hit.metadata.get("source_version")
    if not isinstance(document_ref, str) or not document_ref.strip():
        raise ValueError("retrieval hit metadata document_ref must not be blank")
    if not isinstance(source_version, str) or not source_version.strip():
        raise ValueError("retrieval hit metadata source_version must not be blank")
    return document_ref.strip(), source_version.strip(), hit.chunk_ref


def _json_mapping(value: object, name: str) -> Mapping[str, object]:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"stored {name} is invalid") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"stored {name} is invalid")
    return decoded


def _json_strings(value: object, name: str) -> tuple[str, ...]:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"stored {name} is invalid") from error
    if not isinstance(decoded, list) or any(
        not isinstance(item, str) or not item.strip() for item in decoded
    ):
        raise ValueError(f"stored {name} is invalid")
    return tuple(decoded)


def _metadata_text(metadata: Mapping[str, object], key: str, *, fallback: object) -> str:
    value = metadata.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        value = fallback
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"stored chunk {key} is invalid")
    return value.strip()


def _pages(start: object, end: object) -> tuple[str, ...]:
    values: list[str] = []
    for value in (start, end):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            continue
        text = str(value)
        if text not in values:
            values.append(text)
    return tuple(values)
