"""SQLite persistence for paragraph-to-concept-role source-of-truth data."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from collections.abc import Sequence

from .models import ParagraphConceptRole


class SqliteTaggingRepository:
    """Persist relation projections with document/version scoped replacement."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path) or path.name in {"", ".", ".."}:
            raise ValueError("path must name a SQLite database file")
        if path.exists() and path.is_dir():
            raise ValueError("path must be a file")
        self._path = path.absolute()

    async def replace_relations(
        self,
        document_ref: str,
        source_version: str,
        relations: Sequence[ParagraphConceptRole],
    ) -> None:
        self._validate_scope(document_ref, source_version)
        normalized = tuple(relations)
        if any(not isinstance(item, ParagraphConceptRole) for item in normalized):
            raise ValueError("relations must contain ParagraphConceptRole values")
        keys = tuple((item.paragraph_id, item.canonical_concept, item.content_role.value) for item in normalized)
        if len(keys) != len(set(keys)):
            raise ValueError("relations must be unique")
        await asyncio.to_thread(self._replace, document_ref, source_version, normalized)

    async def replace_chunk_relations(
        self,
        document_ref: str,
        source_version: str,
        paragraph_ids: Sequence[str],
        relations: Sequence[ParagraphConceptRole],
    ) -> None:
        """Atomically replace relations belonging to one explicitly scoped chunk.

        Callers provide the requested paragraph IDs rather than relying on an
        ID prefix, keeping replacement safe when stable-reference formats evolve.
        """
        self._validate_scope(document_ref, source_version)
        paragraph_scope = tuple(paragraph_ids)
        if not paragraph_scope or any(
            not isinstance(item, str) or not item.strip() for item in paragraph_scope
        ):
            raise ValueError("paragraph_ids must contain non-blank strings")
        if len(paragraph_scope) != len(set(paragraph_scope)):
            raise ValueError("paragraph_ids must be unique")
        normalized = tuple(relations)
        if any(not isinstance(item, ParagraphConceptRole) for item in normalized):
            raise ValueError("relations must contain ParagraphConceptRole values")
        if any(item.paragraph_id not in paragraph_scope for item in normalized):
            raise ValueError("relations must belong to paragraph_ids")
        keys = tuple(
            (item.paragraph_id, item.canonical_concept, item.content_role.value)
            for item in normalized
        )
        if len(keys) != len(set(keys)):
            raise ValueError("relations must be unique")
        await asyncio.to_thread(
            self._replace_chunk,
            document_ref,
            source_version,
            paragraph_scope,
            normalized,
        )

    async def list_relations(
        self,
        document_ref: str,
        source_version: str,
    ) -> tuple[ParagraphConceptRole, ...]:
        self._validate_scope(document_ref, source_version)
        return await asyncio.to_thread(self._list, document_ref, source_version)

    def _replace(
        self,
        document_ref: str,
        source_version: str,
        relations: tuple[ParagraphConceptRole, ...],
    ) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            connection.execute(
                "DELETE FROM paragraph_concept_roles WHERE document_ref = ? AND source_version = ?",
                (document_ref, source_version),
            )
            connection.executemany(
                """
                INSERT INTO paragraph_concept_roles
                    (document_ref, source_version, paragraph_id, canonical_concept, content_role)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (document_ref, source_version, item.paragraph_id, item.canonical_concept, item.content_role.value)
                    for item in relations
                ),
            )

    def _list(self, document_ref: str, source_version: str) -> tuple[ParagraphConceptRole, ...]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            rows = connection.execute(
                """
                SELECT paragraph_id, canonical_concept, content_role
                FROM paragraph_concept_roles
                WHERE document_ref = ? AND source_version = ?
                ORDER BY paragraph_id, canonical_concept, content_role
                """,
                (document_ref, source_version),
            ).fetchall()
        return tuple(ParagraphConceptRole(paragraph, concept, role) for paragraph, concept, role in rows)

    def _replace_chunk(
        self,
        document_ref: str,
        source_version: str,
        paragraph_ids: tuple[str, ...],
        relations: tuple[ParagraphConceptRole, ...],
    ) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        placeholders = ", ".join("?" for _ in paragraph_ids)
        with sqlite3.connect(self._path) as connection:
            self._create_schema(connection)
            connection.execute(
                f"DELETE FROM paragraph_concept_roles WHERE document_ref = ? AND source_version = ? AND paragraph_id IN ({placeholders})",
                (document_ref, source_version, *paragraph_ids),
            )
            connection.executemany(
                """
                INSERT INTO paragraph_concept_roles
                    (document_ref, source_version, paragraph_id, canonical_concept, content_role)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (
                        document_ref,
                        source_version,
                        item.paragraph_id,
                        item.canonical_concept,
                        item.content_role.value,
                    )
                    for item in relations
                ),
            )

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS paragraph_concept_roles (
                document_ref TEXT NOT NULL,
                source_version TEXT NOT NULL,
                paragraph_id TEXT NOT NULL,
                canonical_concept TEXT NOT NULL,
                content_role TEXT NOT NULL,
                PRIMARY KEY (document_ref, source_version, paragraph_id, canonical_concept, content_role)
            )
            """
        )

    @staticmethod
    def _validate_scope(document_ref: str, source_version: str) -> None:
        if not isinstance(document_ref, str) or not document_ref.strip():
            raise ValueError("document_ref must not be blank")
        if not isinstance(source_version, str) or not source_version.strip():
            raise ValueError("source_version must not be blank")
