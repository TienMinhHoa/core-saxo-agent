"""Internal service boundaries for document ingestion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
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
    async def sync_pending(
        self,
        *,
        ingestion_run_id: str | None = None,
        limit: int,
    ) -> Mapping[str, object]: ...

    async def pending_count(self, *, ingestion_run_id: str | None = None) -> int: ...


class _Lifecycle(Protocol):
    async def start_or_resume(
        self,
        *,
        ingestion_run_id: str,
        document_ref: str,
        source_version: str,
        source_hash: str,
    ) -> object: ...

    async def mark_tagged_pending_vector_sync(self, ingestion_run_id: str) -> object: ...

    async def mark_ready(
        self,
        ingestion_run_id: str,
        *,
        pending_event_count: int = 0,
    ) -> object: ...

    async def mark_failed(self, ingestion_run_id: str, *, error_code: str) -> object: ...


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
        lifecycle: _Lifecycle | None = None,
        artifact_exporter: _ArtifactExporter | None = None,
    ) -> None:
        if not callable(getattr(ingest_workflow, "execute", None)):
            raise TypeError("ingest workflow must provide execute")
        if vector_sync is not None and not callable(getattr(vector_sync, "sync_pending", None)):
            raise TypeError("vector sync must provide sync_pending")
        if lifecycle is not None and vector_sync is None:
            raise TypeError("lifecycle requires vector sync")
        if lifecycle is not None:
            for method in (
                "start_or_resume",
                "mark_tagged_pending_vector_sync",
                "mark_ready",
                "mark_failed",
            ):
                if not callable(getattr(lifecycle, method, None)):
                    raise TypeError(f"lifecycle must provide {method}")
        if artifact_exporter is not None and not callable(getattr(artifact_exporter, "export", None)):
            raise TypeError("artifact exporter must provide export")
        self._ingest_workflow = ingest_workflow
        self._vector_sync = vector_sync
        self._lifecycle = lifecycle
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
        ingestion_run_id: str | None = None,
        source_hash: str | None = None,
    ) -> IngestionReport:
        if not isinstance(command, IngestionCommand):
            raise TypeError("command must be an IngestionCommand")
        if not isinstance(resolution_profile, str) or not resolution_profile.strip():
            raise ValueError("resolution_profile must not be blank")
        if not isinstance(sync_limit, int) or isinstance(sync_limit, bool) or sync_limit <= 0:
            raise ValueError("sync_limit must be positive")
        self._validate_lifecycle_identity(ingestion_run_id, source_hash)
        if self._lifecycle is not None:
            assert ingestion_run_id is not None
            assert source_hash is not None
            await self._lifecycle.start_or_resume(
                ingestion_run_id=ingestion_run_id,
                document_ref=command.document_ref,
                source_version=command.source_version,
                source_hash=source_hash,
            )
        try:
            report = await self._ingest_workflow.execute(
                command,
                tuple(chunks),
                tuple(paragraphs),
                resolution_profile=resolution_profile,
            )
        except Exception:
            if self._lifecycle is not None:
                await self._lifecycle.mark_failed(ingestion_run_id, error_code="ingestion_exception")
            raise
        if not isinstance(report, IngestionReport):
            raise TypeError("ingest workflow must return IngestionReport")
        if not report.indexed:
            if self._lifecycle is not None:
                await self._lifecycle.mark_failed(ingestion_run_id, error_code="ingestion_failed")
            return report
        if self._lifecycle is not None:
            await self._lifecycle.mark_tagged_pending_vector_sync(ingestion_run_id)
        if report.indexed and self._vector_sync is not None:
            try:
                if self._lifecycle is None:
                    sync_result = await self._vector_sync.sync_pending(limit=sync_limit)
                else:
                    sync_result = await self._vector_sync.sync_pending(
                        ingestion_run_id=ingestion_run_id,
                        limit=sync_limit,
                    )
                failed = _vector_sync_failure_count(sync_result)
                if failed:
                    report = replace(
                        report,
                        indexed=False,
                        vector_sync_failed=failed,
                        errors=(*report.errors, f"vector sync failed for {failed} event(s)"),
                    )
                    if self._lifecycle is not None:
                        await self._lifecycle.mark_failed(
                            ingestion_run_id,
                            error_code="vector_sync_failed",
                        )
                elif self._lifecycle is not None:
                    pending = await _pending_vector_event_count(
                        self._vector_sync,
                        sync_result,
                        ingestion_run_id=ingestion_run_id,
                    )
                    if pending:
                        report = replace(
                            report,
                            indexed=False,
                            errors=(*report.errors, f"vector sync pending for {pending} event(s)"),
                        )
                    else:
                        await self._lifecycle.mark_ready(
                            ingestion_run_id,
                            pending_event_count=0,
                        )
            except Exception:
                if self._lifecycle is not None:
                    await self._lifecycle.mark_failed(
                        ingestion_run_id,
                        error_code="vector_sync_error",
                    )
                raise
        if report.indexed and self._artifact_exporter is not None:
            self._artifact_exporter.export(
                document_ref=command.document_ref,
                source_version=command.source_version,
                paragraphs=tuple(paragraphs),
                relations=tuple(relations),
                ingestion_report=report,
            )
        return report

    def _validate_lifecycle_identity(
        self,
        ingestion_run_id: str | None,
        source_hash: str | None,
    ) -> None:
        if self._lifecycle is None:
            if ingestion_run_id is not None or source_hash is not None:
                raise ValueError("lifecycle identity requires a lifecycle collaborator")
            return
        if not isinstance(ingestion_run_id, str) or not ingestion_run_id.strip():
            raise ValueError("ingestion_run_id must not be blank")
        if not isinstance(source_hash, str) or not source_hash.strip():
            raise ValueError("source_hash must not be blank")


def _vector_sync_failure_count(result: Mapping[str, object]) -> int:
    """Validate the sync summary before it can influence readiness state."""

    if not isinstance(result, Mapping):
        raise TypeError("vector sync must return a mapping")
    for key in ("succeeded", "failed"):
        value = result.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"vector sync {key} count must be a non-negative integer")
    return result["failed"]


async def _pending_vector_event_count(
    vector_sync: _VectorSync,
    result: Mapping[str, object],
    *,
    ingestion_run_id: str,
) -> int:
    pending_count = getattr(vector_sync, "pending_count", None)
    if callable(pending_count):
        value = await pending_count(ingestion_run_id=ingestion_run_id)
    else:
        value = result.get("pending")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("vector sync pending count must be a non-negative integer")
    return value
