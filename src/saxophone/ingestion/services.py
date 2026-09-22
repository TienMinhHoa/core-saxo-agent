"""Internal service boundaries for document ingestion."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .models import IngestionCommand, IngestionReport


class _IngestWorkflow(Protocol):
    async def execute(
        self,
        command: IngestionCommand,
        chunks: Sequence[object],
        paragraphs: Sequence[object],
        *,
        resolution_profile: str,
    ) -> IngestionReport: ...


class _VectorSync(Protocol):
    async def sync_pending(self, *, limit: int) -> dict[str, int]: ...


class _ArtifactExporter(Protocol):
    def export(
        self,
        *,
        document_ref: str,
        source_version: str,
        paragraphs: tuple[object, ...],
        relations: tuple[object, ...],
        ingestion_report: IngestionReport,
    ) -> None: ...


class DocumentIngestionService:
    """Coordinate extraction output with ingestion and durable vector sync.

    Parsing and tagging remain owned by the existing workflow. This boundary
    gives callers one service-first entry point and only drains vectors after
    the relational/index projection reports success.
    """

    def __init__(
        self,
        ingest_workflow: _IngestWorkflow,
        *,
        vector_sync: _VectorSync | None = None,
        artifact_exporter: _ArtifactExporter | None = None,
    ) -> None:
        if not callable(getattr(ingest_workflow, "execute", None)):
            raise TypeError("ingest workflow must provide execute")
        if vector_sync is not None and not callable(getattr(vector_sync, "sync_pending", None)):
            raise TypeError("vector sync must provide sync_pending")
        if artifact_exporter is not None and not callable(getattr(artifact_exporter, "export", None)):
            raise TypeError("artifact exporter must provide export")
        self._ingest_workflow = ingest_workflow
        self._vector_sync = vector_sync
        self._artifact_exporter = artifact_exporter

    async def ingest_document(
        self,
        command: IngestionCommand,
        chunks: Sequence[object],
        paragraphs: Sequence[object],
        *,
        resolution_profile: str,
        sync_limit: int = 100,
        relations: Sequence[object] = (),
    ) -> IngestionReport:
        if not isinstance(command, IngestionCommand):
            raise TypeError("command must be an IngestionCommand")
        if not isinstance(resolution_profile, str) or not resolution_profile.strip():
            raise ValueError("resolution_profile must not be blank")
        if not isinstance(sync_limit, int) or isinstance(sync_limit, bool) or sync_limit <= 0:
            raise ValueError("sync_limit must be positive")
        report = await self._ingest_workflow.execute(
            command,
            tuple(chunks),
            tuple(paragraphs),
            resolution_profile=resolution_profile,
        )
        if not isinstance(report, IngestionReport):
            raise TypeError("ingest workflow must return IngestionReport")
        if report.indexed and self._vector_sync is not None:
            await self._vector_sync.sync_pending(limit=sync_limit)
        if report.indexed and self._artifact_exporter is not None:
            self._artifact_exporter.export(
                document_ref=command.document_ref,
                source_version=command.source_version,
                paragraphs=tuple(paragraphs),
                relations=tuple(relations),
                ingestion_report=report,
            )
        return report
