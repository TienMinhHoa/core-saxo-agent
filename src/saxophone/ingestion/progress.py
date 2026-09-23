"""Structured progress reporting for long-running document ingestion."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic

from saxophone.platform.observability import EventSink, StructuredEvent


class IngestionProgressReporter:
    """Emit payload-free progress with deterministic elapsed and ETA values."""

    def __init__(
        self,
        event_sink: EventSink,
        *,
        ingestion_run_id: str,
        document_ref: str,
        total_chunks: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not callable(getattr(event_sink, "emit", None)):
            raise TypeError("event_sink must provide emit")
        if not isinstance(ingestion_run_id, str) or not ingestion_run_id.strip():
            raise ValueError("ingestion_run_id must not be blank")
        if not isinstance(document_ref, str) or not document_ref.strip():
            raise ValueError("document_ref must not be blank")
        if isinstance(total_chunks, bool) or not isinstance(total_chunks, int) or total_chunks < 1:
            raise ValueError("total_chunks must be positive")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._event_sink = event_sink
        self._ingestion_run_id = ingestion_run_id.strip()
        self._document_ref = document_ref.strip()
        self._total_chunks = total_chunks
        self._clock = clock
        self._started_at = clock()
        self._completed_chunks = 0

    def started(self) -> None:
        self._emit("starting", "started", completed_chunks=0, elapsed=0.0)

    def chunk_started(
        self,
        chunk_id: str,
        *,
        current_chunk: int,
        completed_chunks: int,
    ) -> None:
        self._emit(
            "tagging",
            "started",
            completed_chunks=completed_chunks,
            current_chunk=current_chunk,
            chunk_id=chunk_id,
        )

    def chunk_completed(
        self,
        chunk_id: str,
        *,
        completed_chunks: int,
        reused: bool,
    ) -> None:
        self._emit(
            "tagging",
            "reused" if reused else "completed",
            completed_chunks=completed_chunks,
            current_chunk=completed_chunks,
            chunk_id=chunk_id,
        )

    def chunk_warning(
        self,
        chunk_id: str,
        *,
        current_chunk: int,
        completed_chunks: int,
        reason_code: str,
    ) -> None:
        self._emit(
            "tagging",
            "warning",
            completed_chunks=completed_chunks,
            current_chunk=current_chunk,
            chunk_id=chunk_id,
            reason_code=reason_code,
        )

    def stage_warning(
        self,
        stage: str,
        *,
        completed_chunks: int,
        reason_code: str,
    ) -> None:
        self._emit(
            stage,
            "warning",
            completed_chunks=completed_chunks,
            reason_code=reason_code,
        )

    def stage_started(self, stage: str, *, completed_chunks: int) -> None:
        self._emit(stage, "started", completed_chunks=completed_chunks)

    def completed(self) -> None:
        self._emit("completed", "success", completed_chunks=self._total_chunks)

    def failed(
        self,
        stage: str,
        *,
        completed_chunks: int | None = None,
        reason_code: str,
    ) -> None:
        self._emit(
            stage,
            "failure",
            completed_chunks=(
                self._completed_chunks
                if completed_chunks is None
                else completed_chunks
            ),
            reason_code=reason_code,
        )

    def _emit(
        self,
        stage: str,
        result: str,
        *,
        completed_chunks: int,
        current_chunk: int | None = None,
        chunk_id: str | None = None,
        reason_code: str | None = None,
        elapsed: float | None = None,
    ) -> None:
        if elapsed is None:
            elapsed = max(0.0, self._clock() - self._started_at)
        self._completed_chunks = completed_chunks
        percentage = completed_chunks / self._total_chunks * 100
        eta = None
        if 0 < completed_chunks < self._total_chunks:
            eta = elapsed / completed_chunks * (self._total_chunks - completed_chunks)
        self._event_sink.emit(
            StructuredEvent(
                name="ingestion.progress",
                correlation_id=self._ingestion_run_id,
                task=f"ingestion.{stage}",
                model="none",
                attempt=1,
                duration_ms=elapsed * 1000,
                input_count=self._total_chunks,
                output_count=completed_chunks,
                result=result,
                reason_code=reason_code,
                document_ref=self._document_ref,
                stage=stage,
                chunk_id=chunk_id,
                current_count=current_chunk,
                completed_count=completed_chunks,
                total_count=self._total_chunks,
                progress_percent=round(percentage, 2),
                elapsed_seconds=round(elapsed, 1),
                eta_seconds=None if eta is None else round(eta, 1),
            )
        )
