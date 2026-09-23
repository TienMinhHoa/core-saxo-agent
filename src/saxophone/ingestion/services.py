"""Internal service boundaries for document ingestion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
import inspect
from typing import Protocol

from .models import IngestionCommand, IngestionReport
from .progress import IngestionProgressReporter
from saxophone.platform.observability import EventSink


class _IngestWorkflow(Protocol):
    async def execute(
        self,
        command: IngestionCommand,
        chunks: Sequence[object],
        paragraphs: Sequence[object],
        *,
        resolution_profile: str,
        ingestion_run_id: str | None = None,
        previous_source_versions: Sequence[str] = (),
        progress: IngestionProgressReporter | None = None,
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
    async def get_document(self, document_ref: str) -> object: ...

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
        event_sink: EventSink | None = None,
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
        if event_sink is not None and not callable(getattr(event_sink, "emit", None)):
            raise TypeError("event_sink must provide emit")
        self._ingest_workflow = ingest_workflow
        self._vector_sync = vector_sync
        self._lifecycle = lifecycle
        self._artifact_exporter = artifact_exporter
        self._event_sink = event_sink

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
        normalized_chunks = tuple(chunks)
        normalized_paragraphs = tuple(paragraphs)
        progress = self._create_progress(command, normalized_chunks, ingestion_run_id)
        if progress is not None:
            progress.started()
        previous_source_versions = await _load_previous_source_versions(
            self._lifecycle,
            document_ref=command.document_ref,
            source_version=command.source_version,
        )
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
            report = await _execute_ingest_workflow(
                self._ingest_workflow,
                command,
                normalized_chunks,
                normalized_paragraphs,
                resolution_profile=resolution_profile,
                ingestion_run_id=ingestion_run_id,
                previous_source_versions=previous_source_versions,
                progress=progress,
            )
        except Exception as error:
            if progress is not None:
                progress.failed(
                    "ingestion",
                    reason_code=type(error).__name__,
                )
            if self._lifecycle is not None:
                await self._lifecycle.mark_failed(ingestion_run_id, error_code="ingestion_exception")
            raise
        if not isinstance(report, IngestionReport):
            raise TypeError("ingest workflow must return IngestionReport")
        if not report.indexed:
            if progress is not None:
                if report.errors:
                    progress.failed("indexing", reason_code="ingestion_failed")
                else:
                    progress.stage_warning(
                        "indexing",
                        completed_chunks=report.chunk_count,
                        reason_code="ingestion_incomplete",
                    )
            if self._lifecycle is not None:
                await self._lifecycle.mark_failed(ingestion_run_id, error_code="ingestion_failed")
            return report
        if self._lifecycle is not None:
            await self._lifecycle.mark_tagged_pending_vector_sync(ingestion_run_id)
        if report.indexed and self._vector_sync is not None:
            try:
                if progress is not None:
                    progress.stage_started(
                        "vector_sync",
                        completed_chunks=len(normalized_chunks),
                    )
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
                    if progress is not None:
                        progress.failed(
                            "vector_sync",
                            reason_code="vector_sync_failed",
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
                        if progress is not None:
                            progress.failed(
                                "vector_sync",
                                reason_code="vector_sync_pending",
                            )
                    else:
                        await self._lifecycle.mark_ready(
                            ingestion_run_id,
                            pending_event_count=0,
                        )
            except Exception as error:
                if progress is not None:
                    progress.failed(
                        "vector_sync",
                        reason_code=type(error).__name__,
                    )
                if self._lifecycle is not None:
                    await self._lifecycle.mark_failed(
                        ingestion_run_id,
                        error_code="vector_sync_error",
                    )
                raise
        if report.indexed and self._artifact_exporter is not None:
            if progress is not None:
                progress.stage_started(
                    "artifact_export",
                    completed_chunks=len(normalized_chunks),
                )
            self._artifact_exporter.export(
                document_ref=command.document_ref,
                source_version=command.source_version,
                paragraphs=tuple(paragraphs),
                relations=tuple(relations),
                ingestion_report=report,
            )
        if report.indexed and progress is not None:
            progress.completed()
        return report

    def _create_progress(
        self,
        command: IngestionCommand,
        chunks: Sequence[object],
        ingestion_run_id: str | None,
    ) -> IngestionProgressReporter | None:
        if self._event_sink is None or not chunks:
            return None
        run_id = ingestion_run_id or (
            f"{command.document_ref}-{command.source_version[:12]}"
        )
        return IngestionProgressReporter(
            self._event_sink,
            ingestion_run_id=run_id,
            document_ref=command.document_ref,
            total_chunks=len(chunks),
        )

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


async def _execute_ingest_workflow(
    workflow: _IngestWorkflow,
    command: IngestionCommand,
    chunks: Sequence[object],
    paragraphs: Sequence[object],
    *,
    resolution_profile: str,
    ingestion_run_id: str | None,
    previous_source_versions: Sequence[str],
    progress: IngestionProgressReporter | None,
) -> IngestionReport:
    """Pass optional run and re-ingestion identity to capable workflows."""

    execute = workflow.execute
    parameters = inspect.signature(execute).parameters
    accepts_run_id = "ingestion_run_id" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    accepts_previous_versions = "previous_source_versions" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    accepts_progress = "progress" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    kwargs: dict[str, object] = {"resolution_profile": resolution_profile}
    if accepts_run_id:
        kwargs["ingestion_run_id"] = ingestion_run_id
    if accepts_previous_versions:
        kwargs["previous_source_versions"] = previous_source_versions
    if accepts_progress:
        kwargs["progress"] = progress
    return await execute(command, chunks, paragraphs, **kwargs)


async def _load_previous_source_versions(
    lifecycle: _Lifecycle | None,
    *,
    document_ref: str,
    source_version: str,
) -> tuple[str, ...]:
    """Load the active version without making first ingestion a special case."""

    if lifecycle is None:
        return ()
    get_document = getattr(lifecycle, "get_document", None)
    if not callable(get_document):
        return ()
    try:
        document = await get_document(document_ref)
    except FileNotFoundError:
        return ()
    active_version = getattr(document, "active_version", None)
    if active_version is None or active_version == source_version:
        return ()
    if not isinstance(active_version, str) or not active_version.strip():
        raise ValueError("lifecycle document active_version must be blank or a string")
    return (active_version,)
