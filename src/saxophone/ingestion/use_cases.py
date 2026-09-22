"""Application use cases for publishing validated ingestion projections."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from saxophone.documents import KnowledgeChunk, KnowledgeRepository
from saxophone.tagging import ParagraphBlock, TagAndPersistParagraph, TaggedParagraph
from saxophone.tagging.chunk_models import ChunkParagraphTaggingInput, ChunkTaggingRequest
from saxophone.tagging.chunk_service import ChunkTaggingRun, ChunkTaggingTransactionService
from saxophone.tagging.vector_outbox import VectorOutboxEvent

from .models import (
    ChunkIndexRecord,
    EmbeddingRecord,
    IndexInputRecord,
    IngestionCommand,
    IngestionReport,
    IngestionSourceChunk,
)
from .ports import EmbeddingProvider, EmbeddingReuseStore, VectorIndex
from .vector_events import build_chunk_vector_upsert_events
from .vector_state import (
    VectorStateReconciliation,
    build_chunk_vector_states,
    build_stale_delete_events,
)


@dataclass(frozen=True, slots=True)
class _PreparedIndex:
    """Embedding-ready records kept separate from their publication side effect."""

    input_records: tuple[IndexInputRecord, ...]
    indexed_records: tuple[ChunkIndexRecord, ...]
    reused_count: int


@dataclass(frozen=True, slots=True)
class _PreparedChunkTagging:
    """Validated chunk requests/results waiting for one atomic commit each."""

    requests: tuple[ChunkTaggingRequest, ...]
    runs: tuple[ChunkTaggingRun, ...]


class _VectorStatePlanner(Protocol):
    async def plan_reconciliation(
        self,
        *,
        entity_type: str,
        collection_name: str,
        index_version: str,
        desired: Sequence[object],
        document_ref: str | None = None,
    ) -> VectorStateReconciliation: ...


class IndexDocument:
    """Publish one document's searchable chunks through the vector-index port."""

    def __init__(
        self,
        vector_index: VectorIndex,
        embedding_provider: EmbeddingProvider,
        embedding_reuse: EmbeddingReuseStore | None = None,
        *,
        knowledge_repository: KnowledgeRepository | None = None,
    ) -> None:
        self._vector_index = vector_index
        self._embedding_provider = embedding_provider
        self._embedding_reuse = embedding_reuse
        self._knowledge_repository = knowledge_repository

    async def execute(
        self,
        command: IngestionCommand,
        records: Sequence[IndexInputRecord],
        *,
        paragraph_count: int | None = None,
        tagged_paragraph_count: int | None = None,
    ) -> IngestionReport:
        normalized_records = tuple(records)
        self._validate_scope(command, normalized_records)
        report_paragraph_count = (
            len(normalized_records) if paragraph_count is None else paragraph_count
        )
        report_tagged_count = (
            sum(1 for record in normalized_records if record.metadata.get("tags"))
            if tagged_paragraph_count is None
            else tagged_paragraph_count
        )
        self._validate_report_counts(report_paragraph_count, report_tagged_count)
        if not normalized_records:
            return self._failure_report(
                command,
                normalized_records,
                paragraph_count=report_paragraph_count,
                tagged_count=report_tagged_count,
                embedded_count=0,
                reused_count=0,
                error=ValueError("cannot index an empty projection"),
            )
        try:
            prepared = await self.prepare(command, normalized_records)
        except Exception as error:
            return self._failure_report(
                command,
                normalized_records,
                paragraph_count=report_paragraph_count,
                tagged_count=report_tagged_count,
                embedded_count=0,
                reused_count=0,
                error=error,
            )
        return await self.publish(
            command,
            prepared,
            paragraph_count=report_paragraph_count,
            tagged_paragraph_count=report_tagged_count,
        )

    async def prepare(
        self,
        command: IngestionCommand,
        records: Sequence[IndexInputRecord],
    ) -> _PreparedIndex:
        """Embed records without publishing them to the vector index."""

        normalized_records = tuple(records)
        self._validate_scope(command, normalized_records)
        if not normalized_records:
            raise ValueError("cannot index an empty projection")
        indexed_records, reused_count = await self._embed_records(command, normalized_records)
        return _PreparedIndex(
            input_records=normalized_records,
            indexed_records=indexed_records,
            reused_count=reused_count,
        )

    async def publish(
        self,
        command: IngestionCommand,
        prepared: _PreparedIndex,
        *,
        paragraph_count: int,
        tagged_paragraph_count: int,
        publish_vectors: bool = True,
    ) -> IngestionReport:
        """Persist the prepared projection and optionally publish vector records."""

        if not isinstance(prepared, _PreparedIndex):
            raise TypeError("prepared must be an embedding preparation")
        normalized_records = prepared.input_records
        self._validate_scope(command, normalized_records)
        self._validate_report_counts(paragraph_count, tagged_paragraph_count)
        try:
            list_chunk_ids = getattr(self._vector_index, "list_chunk_ids", None)
            existing_ids = ()
            if publish_vectors and list_chunk_ids is not None:
                existing_ids = await list_chunk_ids(document_ref=command.document_ref)
            if self._knowledge_repository is not None:
                for record in prepared.indexed_records:
                    await self._knowledge_repository.upsert(_knowledge_chunk(record))
            if publish_vectors:
                await self._vector_index.upsert_chunks(prepared.indexed_records)
                if list_chunk_ids is not None:
                    current_ids = {record.chunk_id for record in prepared.indexed_records}
                    stale_ids = tuple(
                        chunk_id for chunk_id in existing_ids if chunk_id not in current_ids
                    )
                    await self._vector_index.delete_chunks(stale_ids)
        except Exception as error:
            return self._failure_report(
                command,
                normalized_records,
                paragraph_count=paragraph_count,
                tagged_count=tagged_paragraph_count,
                embedded_count=len(prepared.indexed_records),
                reused_count=prepared.reused_count,
                error=error,
            )
        return IngestionReport(
            document_ref=command.document_ref,
            source_version=command.source_version,
            chunk_count=len(normalized_records),
            paragraph_count=paragraph_count,
            tagged_paragraph_count=tagged_paragraph_count,
            failed_paragraph_count=0,
            embedded_count=len(normalized_records) - prepared.reused_count,
            reused_embedding_count=prepared.reused_count,
            skipped_count=0,
            index_version=command.index_profile,
            indexed=True,
            warnings=(),
            errors=(),
        )

    def failure_report(
        self,
        command: IngestionCommand,
        records: Sequence[IndexInputRecord],
        *,
        paragraph_count: int,
        tagged_count: int,
        embedded_count: int,
        reused_count: int,
        error: Exception,
    ) -> IngestionReport:
        """Build the same typed failure report used by the one-step workflow."""

        return self._failure_report(
            command,
            records,
            paragraph_count=paragraph_count,
            tagged_count=tagged_count,
            embedded_count=embedded_count,
            reused_count=reused_count,
            error=error,
        )

    async def _embed_records(
        self,
        command: IngestionCommand,
        records: Sequence[IndexInputRecord],
    ) -> tuple[tuple[ChunkIndexRecord, ...], int]:
        cached = (
            dict(await self._embedding_reuse.find(records))
            if self._embedding_reuse is not None
            else {}
        )
        missing = tuple(record for record in records if record.chunk_id not in cached)
        embeddings = await self._embedding_provider.embed(
            tuple((record.chunk_id, record.search_text) for record in missing),
            source_version=command.source_version,
        ) if missing else ()
        if len(embeddings) != len(missing):
            raise ValueError("embedding count does not match chunk count")
        for record, embedding in zip(missing, embeddings):
            self._validate_embedding(command, record, embedding)
            cached[record.chunk_id] = ChunkIndexRecord(
                chunk_id=record.chunk_id,
                document_ref=record.document_ref,
                source_version=record.source_version,
                search_text=record.search_text,
                embedding=embedding.vector,
                embedding_profile=record.embedding_profile,
                access_scope=record.access_scope,
                metadata=record.metadata,
            )
        resolved = tuple(cached[record.chunk_id] for record in records)
        dimensions = {record.dimension for record in resolved}
        if len(dimensions) > 1:
            raise ValueError("embedding dimensions must match")
        if self._embedding_reuse is not None and missing:
            await self._embedding_reuse.save(tuple(cached[record.chunk_id] for record in missing))
        return resolved, len(records) - len(missing)

    @staticmethod
    def _validate_embedding(
        command: IngestionCommand,
        record: IndexInputRecord,
        embedding: EmbeddingRecord,
    ) -> None:
        if embedding.chunk_id != record.chunk_id:
            raise ValueError("embedding chunk ID does not match record")
        if embedding.source_version != command.source_version:
            raise ValueError("embedding source version does not match command")
        if embedding.model_profile != command.embedding_profile:
            raise ValueError("embedding model profile does not match command")

    @staticmethod
    def _failure_report(
        command: IngestionCommand,
        records: Sequence[IndexInputRecord],
        *,
        paragraph_count: int,
        tagged_count: int,
        embedded_count: int,
        reused_count: int,
        error: Exception,
    ) -> IngestionReport:
        return IngestionReport(
            document_ref=command.document_ref,
            source_version=command.source_version,
            chunk_count=len(records),
            paragraph_count=paragraph_count,
            tagged_paragraph_count=tagged_count,
            failed_paragraph_count=len(records),
            embedded_count=embedded_count,
            reused_embedding_count=reused_count,
            skipped_count=0,
            index_version=command.index_profile,
            indexed=False,
            warnings=(),
            errors=(str(error),),
        )

    @staticmethod
    def _validate_report_counts(paragraph_count: int, tagged_count: int) -> None:
        if paragraph_count < 0:
            raise ValueError("paragraph_count must not be negative")
        if tagged_count < 0:
            raise ValueError("tagged_paragraph_count must not be negative")
        if tagged_count > paragraph_count:
            raise ValueError("tagged_paragraph_count must not exceed paragraph_count")

    @staticmethod
    def _validate_scope(
        command: IngestionCommand,
        records: Sequence[IndexInputRecord],
    ) -> None:
        for record in records:
            if record.document_ref != command.document_ref:
                raise ValueError("all records must belong to the command document")
            if record.source_version != command.source_version:
                raise ValueError("all records must match the command source version")
            if record.embedding_profile != command.embedding_profile:
                raise ValueError("all records must match the command embedding profile")
            if record.access_scope != command.access_scope:
                raise ValueError("all records must match the command access scope")


class DocumentChunkTaggingService:
    """Build, validate, and commit one chunk-tagging call per source chunk."""

    def __init__(self, transaction_service: ChunkTaggingTransactionService) -> None:
        if not isinstance(transaction_service, ChunkTaggingTransactionService):
            raise TypeError("transaction_service must be a ChunkTaggingTransactionService")
        self._transaction_service = transaction_service

    async def execute(
        self,
        command: IngestionCommand,
        chunks: Sequence[IngestionSourceChunk],
        paragraphs: Sequence[ParagraphBlock],
        *,
        existing_candidates: Mapping[str, Sequence[str]] | None = None,
        outbox_events: Mapping[str, Sequence[VectorOutboxEvent]] | None = None,
    ) -> tuple[ChunkTaggingRun, ...]:
        prepared = await self.prepare(
            command,
            chunks,
            paragraphs,
            existing_candidates=existing_candidates,
        )
        await self.commit(
            command,
            prepared,
            outbox_events=outbox_events,
        )
        return prepared.runs

    async def prepare(
        self,
        command: IngestionCommand,
        chunks: Sequence[IngestionSourceChunk],
        paragraphs: Sequence[ParagraphBlock],
        *,
        existing_candidates: Mapping[str, Sequence[str]] | None = None,
    ) -> _PreparedChunkTagging:
        """Run provider calls and return validated results before persistence."""

        if not isinstance(command, IngestionCommand):
            raise TypeError("command must be an IngestionCommand")
        normalized_chunks = tuple(chunks)
        normalized_paragraphs = tuple(paragraphs)
        _validate_chunk_tagging_inputs(command, normalized_chunks, normalized_paragraphs)
        requests = build_chunk_tagging_requests(
            normalized_chunks,
            normalized_paragraphs,
            existing_candidates=existing_candidates,
        )
        runs: list[ChunkTaggingRun] = []
        for request in requests:
            runs.append(await self._transaction_service.tag(request))
        return _PreparedChunkTagging(tuple(requests), tuple(runs))

    async def commit(
        self,
        command: IngestionCommand,
        prepared: _PreparedChunkTagging,
        *,
        outbox_events: Mapping[str, Sequence[VectorOutboxEvent]] | None = None,
    ) -> None:
        """Commit prepared chunk relations and vector events atomically per chunk."""

        if not isinstance(command, IngestionCommand):
            raise TypeError("command must be an IngestionCommand")
        if not isinstance(prepared, _PreparedChunkTagging):
            raise TypeError("prepared must be a chunk tagging preparation")
        if len(prepared.requests) != len(prepared.runs):
            raise ValueError("prepared requests and runs must have matching lengths")
        events_by_chunk = _normalize_outbox_events(
            outbox_events,
            tuple(request.chunk_id for request in prepared.requests),
        )
        for request, run in zip(prepared.requests, prepared.runs):
            await self._transaction_service.commit(
                command.document_ref,
                command.source_version,
                request,
                run,
                outbox_events=events_by_chunk.get(request.chunk_id, ()),
            )

    async def commit_document(
        self,
        command: IngestionCommand,
        prepared: _PreparedChunkTagging,
        *,
        outbox_events: Sequence[VectorOutboxEvent] = (),
        concept_outbox_events: Sequence[VectorOutboxEvent] = (),
        previous_source_versions: Sequence[str] = (),
    ) -> None:
        """Commit all prepared chunks through one document transaction."""

        if not isinstance(command, IngestionCommand):
            raise TypeError("command must be an IngestionCommand")
        if not isinstance(prepared, _PreparedChunkTagging):
            raise TypeError("prepared must be a chunk tagging preparation")
        commit_kwargs = {
            "outbox_events": outbox_events,
            "previous_source_versions": previous_source_versions,
        }
        if concept_outbox_events:
            commit_kwargs["concept_outbox_events"] = concept_outbox_events
        await self._transaction_service.commit_document(
            command.document_ref,
            command.source_version,
            prepared.requests,
            prepared.runs,
            **commit_kwargs,
        )


def build_chunk_tagging_requests(
    chunks: Sequence[IngestionSourceChunk],
    paragraphs: Sequence[ParagraphBlock],
    *,
    existing_candidates: Mapping[str, Sequence[str]] | None = None,
) -> tuple[ChunkTaggingRequest, ...]:
    """Project source paragraphs into deterministic, context-rich chunk requests."""

    normalized_chunks = tuple(chunks)
    normalized_paragraphs = tuple(paragraphs)
    if any(not isinstance(chunk, IngestionSourceChunk) for chunk in normalized_chunks):
        raise ValueError("chunks must contain IngestionSourceChunk values")
    if any(not isinstance(paragraph, ParagraphBlock) for paragraph in normalized_paragraphs):
        raise ValueError("paragraphs must contain ParagraphBlock values")

    chunk_ids = tuple(chunk.chunk_id for chunk in normalized_chunks)
    if len(set(chunk_ids)) != len(chunk_ids):
        raise ValueError("chunk IDs must be unique")
    paragraph_ids = tuple(paragraph.paragraph_id for paragraph in normalized_paragraphs)
    if len(set(paragraph_ids)) != len(paragraph_ids):
        raise ValueError("paragraph IDs must be unique")
    chunk_id_set = set(chunk_ids)
    if any(paragraph.chunk_id not in chunk_id_set for paragraph in normalized_paragraphs):
        raise ValueError("all paragraphs must belong to a supplied chunk")

    candidates = _normalize_existing_candidates(existing_candidates, set(paragraph_ids))
    grouped: dict[str, list[ParagraphBlock]] = {chunk_id: [] for chunk_id in chunk_ids}
    for paragraph in normalized_paragraphs:
        grouped[paragraph.chunk_id].append(paragraph)

    requests: list[ChunkTaggingRequest] = []
    for chunk in normalized_chunks:
        ordered = sorted(grouped[chunk.chunk_id], key=lambda item: item.ordinal)
        if not ordered:
            raise ValueError("every chunk must have at least one paragraph")
        if len({paragraph.ordinal for paragraph in ordered}) != len(ordered):
            raise ValueError("paragraph ordinals must be unique within a chunk")
        inputs = tuple(
            ChunkParagraphTaggingInput(
                paragraph,
                existing_candidates=candidates.get(paragraph.paragraph_id, ()),
                previous_context=ordered[index - 1].text if index else "",
                next_context=ordered[index + 1].text if index + 1 < len(ordered) else "",
                image_context=tuple(
                    paragraph.image_captions[image_ref]
                    for image_ref in paragraph.image_refs
                    if image_ref in paragraph.image_captions
                ),
            )
            for index, paragraph in enumerate(ordered)
        )
        requests.append(ChunkTaggingRequest(chunk.chunk_id, inputs))
    return tuple(requests)


class IngestDocument:
    """Coordinate paragraph tagging, persistence, embedding, and indexing.

    The coordinator deliberately accepts normalized chunks and paragraphs.
    Extraction and Markdown parsing remain separate use cases; this boundary
    only transfers validated state between ingestion stages.
    """

    def __init__(
        self,
        tag_and_persist: TagAndPersistParagraph | None,
        index_document: IndexDocument,
        *,
        chunk_tagging: DocumentChunkTaggingService | None = None,
        vector_state: _VectorStatePlanner | None = None,
    ) -> None:
        if tag_and_persist is None and chunk_tagging is None:
            raise ValueError("a paragraph or chunk tagging workflow is required")
        if tag_and_persist is not None and chunk_tagging is not None:
            raise ValueError("paragraph and chunk tagging workflows are mutually exclusive")
        if chunk_tagging is not None and not isinstance(
            chunk_tagging, DocumentChunkTaggingService
        ):
            raise TypeError("chunk_tagging must be a DocumentChunkTaggingService")
        if vector_state is not None and not callable(
            getattr(vector_state, "plan_reconciliation", None)
        ):
            raise TypeError("vector_state must provide plan_reconciliation")
        self._tag_and_persist = tag_and_persist
        self._index_document = index_document
        self._chunk_tagging = chunk_tagging
        self._vector_state = vector_state

    async def execute(
        self,
        command: IngestionCommand,
        chunks: Sequence[IngestionSourceChunk],
        paragraphs: Sequence[ParagraphBlock],
        *,
        resolution_profile: str,
        existing_candidates: Mapping[str, Sequence[str]] | None = None,
        outbox_events: Mapping[str, Sequence[VectorOutboxEvent]] | None = None,
        concept_outbox_events: Sequence[VectorOutboxEvent] = (),
        ingestion_run_id: str | None = None,
        previous_source_versions: Sequence[str] = (),
    ) -> IngestionReport:
        normalized_chunks = tuple(chunks)
        normalized_paragraphs = tuple(paragraphs)
        self._validate_input_scope(command, normalized_chunks, normalized_paragraphs)
        _validate_optional_ingestion_run_id(ingestion_run_id)
        normalized_previous_versions = _normalize_previous_source_versions(
            ingestion_run_id,
            previous_source_versions,
        )
        normalized_concept_events = _normalize_concept_outbox_events(
            concept_outbox_events,
            ingestion_run_id=ingestion_run_id,
        )

        if self._chunk_tagging is not None:
            prepared_tagging = await self._chunk_tagging.prepare(
                command,
                normalized_chunks,
                normalized_paragraphs,
                existing_candidates=existing_candidates,
            )
            tagged = _tagged_paragraphs_from_chunk_runs(
                normalized_paragraphs, prepared_tagging.runs
            )
            records = build_index_inputs(command, normalized_chunks, tagged)
            try:
                prepared_index = await self._index_document.prepare(command, records)
            except Exception as error:
                return self._index_document.failure_report(
                    command,
                    records,
                    paragraph_count=len(normalized_paragraphs),
                    tagged_count=len(tagged),
                    embedded_count=0,
                    reused_count=0,
                    error=error,
                )
            reconciliation = await self._plan_vector_reconciliation(
                command,
                prepared_index,
                ingestion_run_id=ingestion_run_id,
            )
            provided_events = _normalize_outbox_events(outbox_events, normalized_chunks)
            allowed_chunk_ids = (
                {state.entity_key for state in reconciliation.upsert_required}
                if reconciliation is not None
                else None
            )
            provided_events = _filter_chunk_upsert_events(
                provided_events,
                allowed_chunk_ids=allowed_chunk_ids,
            )
            events_by_chunk = _merge_outbox_events(
                provided_events,
                _generated_chunk_events(
                    prepared_index,
                    command,
                    ingestion_run_id=ingestion_run_id,
                    allowed_chunk_ids=allowed_chunk_ids,
                ),
            )
            if ingestion_run_id is None:
                await self._chunk_tagging.commit(
                    command,
                    prepared_tagging,
                    outbox_events=events_by_chunk,
                )
            else:
                document_events = tuple(
                    event
                    for request in prepared_tagging.requests
                    for event in events_by_chunk.get(request.chunk_id, ())
                )
                stale_events = (
                    build_stale_delete_events(
                        reconciliation,
                        ingestion_run_id=ingestion_run_id,
                        document_ref=command.document_ref,
                        source_version=command.source_version,
                    )
                    if reconciliation is not None
                    else ()
                )
                document_events = _append_unique_events(document_events, stale_events)
                await self._chunk_tagging.commit_document(
                    command,
                    prepared_tagging,
                    outbox_events=document_events,
                    concept_outbox_events=normalized_concept_events,
                    previous_source_versions=normalized_previous_versions,
                )
            return await self._index_document.publish(
                command,
                prepared_index,
                paragraph_count=len(normalized_paragraphs),
                tagged_paragraph_count=len(tagged),
                publish_vectors=ingestion_run_id is None,
            )
        else:
            if (
                existing_candidates is not None
                or outbox_events is not None
                or normalized_concept_events
                or ingestion_run_id is not None
            ):
                raise ValueError("chunk tagging options require a chunk tagging workflow")
            assert self._tag_and_persist is not None
            tagged = {}
            for paragraph in normalized_paragraphs:
                tagged[paragraph.paragraph_id] = await self._tag_and_persist.execute(
                    paragraph,
                    tagging_profile=command.tagging_profile,
                    resolution_profile=resolution_profile,
                )

        records = build_index_inputs(command, normalized_chunks, tagged)
        return await self._index_document.execute(
            command,
            records,
            paragraph_count=len(normalized_paragraphs),
            tagged_paragraph_count=len(tagged),
        )

    @staticmethod
    def _validate_input_scope(
        command: IngestionCommand,
        chunks: Sequence[IngestionSourceChunk],
        paragraphs: Sequence[ParagraphBlock],
    ) -> None:
        chunk_ids = set()
        for chunk in chunks:
            _validate_chunk_scope(command, chunk)
            if chunk.chunk_id in chunk_ids:
                raise ValueError("chunk IDs must be unique")
            chunk_ids.add(chunk.chunk_id)

        paragraph_ids = set()
        for paragraph in paragraphs:
            if paragraph.paragraph_id in paragraph_ids:
                raise ValueError("paragraph IDs must be unique")
            if paragraph.chunk_id not in chunk_ids:
                raise ValueError("all paragraphs must belong to a supplied chunk")
            paragraph_ids.add(paragraph.paragraph_id)

    async def _plan_vector_reconciliation(
        self,
        command: IngestionCommand,
        prepared: _PreparedIndex,
        *,
        ingestion_run_id: str | None,
    ) -> VectorStateReconciliation | None:
        if ingestion_run_id is None or self._vector_state is None:
            return None
        desired = build_chunk_vector_states(
            prepared.indexed_records,
            index_version=command.index_profile,
        )
        reconciliation = await self._vector_state.plan_reconciliation(
            entity_type="chunk",
            collection_name="document_chunks",
            index_version=command.index_profile,
            desired=desired,
            document_ref=command.document_ref,
        )
        if not isinstance(reconciliation, VectorStateReconciliation):
            raise TypeError("vector_state must return VectorStateReconciliation")
        return reconciliation


def _validate_chunk_tagging_inputs(
    command: IngestionCommand,
    chunks: Sequence[IngestionSourceChunk],
    paragraphs: Sequence[ParagraphBlock],
) -> None:
    if any(not isinstance(chunk, IngestionSourceChunk) for chunk in chunks):
        raise ValueError("chunks must contain IngestionSourceChunk values")
    if any(not isinstance(paragraph, ParagraphBlock) for paragraph in paragraphs):
        raise ValueError("paragraphs must contain ParagraphBlock values")
    IngestDocument._validate_input_scope(command, chunks, paragraphs)


def _normalize_existing_candidates(
    candidates: Mapping[str, Sequence[str]] | None,
    paragraph_ids: set[str],
) -> dict[str, tuple[str, ...]]:
    if candidates is None:
        return {}
    if not isinstance(candidates, Mapping):
        raise ValueError("existing_candidates must be a mapping")
    unknown = set(candidates) - paragraph_ids
    if unknown:
        raise ValueError("existing_candidates contains an unknown paragraph ID")
    normalized: dict[str, tuple[str, ...]] = {}
    for paragraph_id, values in candidates.items():
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            raise ValueError("existing candidates must be sequences of strings")
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("existing candidates must contain non-blank strings")
        normalized_values = tuple(value.strip() for value in values)
        if len(set(normalized_values)) != len(normalized_values):
            raise ValueError("existing candidates must not contain duplicates")
        normalized[paragraph_id] = normalized_values
    return normalized


def _normalize_outbox_events(
    events: Mapping[str, Sequence[VectorOutboxEvent]] | None,
    chunks_or_ids: Sequence[IngestionSourceChunk | str],
) -> dict[str, tuple[VectorOutboxEvent, ...]]:
    if events is None:
        return {}
    if not isinstance(events, Mapping):
        raise ValueError("outbox_events must be a mapping")
    chunk_ids = {
        item.chunk_id if isinstance(item, IngestionSourceChunk) else item
        for item in chunks_or_ids
    }
    if set(events) - chunk_ids:
        raise ValueError("outbox_events contains an unknown chunk ID")
    normalized: dict[str, tuple[VectorOutboxEvent, ...]] = {}
    for chunk_id, values in events.items():
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            raise ValueError("outbox events must be sequences")
        normalized_values = tuple(values)
        if any(not isinstance(value, VectorOutboxEvent) for value in normalized_values):
            raise ValueError("outbox events must contain VectorOutboxEvent values")
        if len({value.event_id for value in normalized_values}) != len(normalized_values):
            raise ValueError("outbox events must not contain duplicate event IDs")
        normalized[chunk_id] = normalized_values
    return normalized


def _normalize_concept_outbox_events(
    events: Sequence[VectorOutboxEvent],
    *,
    ingestion_run_id: str | None,
) -> tuple[VectorOutboxEvent, ...]:
    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
        raise ValueError("concept_outbox_events must be a sequence")
    normalized = tuple(events)
    if normalized and ingestion_run_id is None:
        raise ValueError("concept_outbox_events require an ingestion_run_id")
    if any(not isinstance(event, VectorOutboxEvent) for event in normalized):
        raise ValueError("concept_outbox_events must contain VectorOutboxEvent values")
    if len({event.event_id for event in normalized}) != len(normalized):
        raise ValueError("concept_outbox_events must not contain duplicate event IDs")
    if any(event.collection != "concept_catalog" for event in normalized):
        raise ValueError("concept outbox events must target concept_catalog")
    if any(event.ingestion_run_id != ingestion_run_id for event in normalized):
        raise ValueError("concept outbox events must match the ingestion_run_id")
    return normalized


def _generated_chunk_events(
    prepared: _PreparedIndex,
    command: IngestionCommand,
    *,
    ingestion_run_id: str | None,
    allowed_chunk_ids: set[str] | None = None,
) -> dict[str, tuple[VectorOutboxEvent, ...]]:
    if ingestion_run_id is None:
        return {}
    records = tuple(
        record
        for record in prepared.indexed_records
        if allowed_chunk_ids is None or record.chunk_id in allowed_chunk_ids
    )
    events = build_chunk_vector_upsert_events(
        records,
        index_version=command.index_profile,
        ingestion_run_id=ingestion_run_id,
    )
    return {event.record_id: (event,) for event in events}


def _filter_chunk_upsert_events(
    events: Mapping[str, Sequence[VectorOutboxEvent]],
    *,
    allowed_chunk_ids: set[str] | None,
) -> dict[str, tuple[VectorOutboxEvent, ...]]:
    if allowed_chunk_ids is None:
        return {chunk_id: tuple(values) for chunk_id, values in events.items()}
    filtered: dict[str, tuple[VectorOutboxEvent, ...]] = {}
    for chunk_id, values in events.items():
        kept = tuple(
            event
            for event in values
            if not (
                event.collection == "document_chunks"
                and event.operation == "upsert"
                and event.record_id not in allowed_chunk_ids
            )
        )
        if kept:
            filtered[chunk_id] = kept
    return filtered


def _append_unique_events(
    existing: Sequence[VectorOutboxEvent],
    additional: Sequence[VectorOutboxEvent],
) -> tuple[VectorOutboxEvent, ...]:
    combined = (*existing, *additional)
    if len({event.event_id for event in combined}) != len(combined):
        raise ValueError("outbox events must not contain duplicate event IDs")
    return combined


def _merge_outbox_events(
    provided: Mapping[str, Sequence[VectorOutboxEvent]] | None,
    generated: Mapping[str, Sequence[VectorOutboxEvent]],
) -> dict[str, tuple[VectorOutboxEvent, ...]]:
    if provided is None:
        provided = {}
    merged: dict[str, tuple[VectorOutboxEvent, ...]] = {}
    event_ids: set[str] = set()
    for source in (provided, generated):
        for chunk_id, events in source.items():
            normalized = tuple(events)
            if any(not isinstance(event, VectorOutboxEvent) for event in normalized):
                raise ValueError("outbox events must contain VectorOutboxEvent values")
            for event in normalized:
                if event.event_id in event_ids:
                    raise ValueError("outbox events must not contain duplicate event IDs")
                event_ids.add(event.event_id)
            merged[chunk_id] = (*merged.get(chunk_id, ()), *normalized)
    return merged


def _validate_optional_ingestion_run_id(ingestion_run_id: str | None) -> None:
    if ingestion_run_id is not None and (
        not isinstance(ingestion_run_id, str) or not ingestion_run_id.strip()
    ):
        raise ValueError("ingestion_run_id must be blank or null")


def _normalize_previous_source_versions(
    ingestion_run_id: str | None,
    previous_source_versions: Sequence[str],
) -> tuple[str, ...]:
    if isinstance(previous_source_versions, (str, bytes)) or not isinstance(
        previous_source_versions, Sequence
    ):
        raise ValueError("previous_source_versions must be a sequence")
    normalized = tuple(previous_source_versions)
    if any(not isinstance(value, str) or not value.strip() for value in normalized):
        raise ValueError("previous_source_versions must contain non-blank strings")
    if len(normalized) != len(set(normalized)):
        raise ValueError("previous_source_versions must be unique")
    if ingestion_run_id is None and normalized:
        raise ValueError("previous_source_versions require an ingestion_run_id")
    return normalized


def _tagged_paragraphs_from_chunk_runs(
    paragraphs: Sequence[ParagraphBlock],
    runs: Sequence[ChunkTaggingRun],
) -> dict[str, TaggedParagraph]:
    source_by_id = {paragraph.paragraph_id: paragraph for paragraph in paragraphs}
    projections: dict[str, TaggedParagraph] = {}
    for run in runs:
        for result in run.result.paragraphs:
            paragraph = source_by_id.get(result.paragraph_ref)
            if paragraph is None:
                raise ValueError("chunk tagging result contains an unknown paragraph reference")
            if result.paragraph_ref in projections:
                raise ValueError("chunk tagging results must not repeat paragraph references")
            generated = tuple(label.generated_concept for label in result.labels)
            resolved = tuple(dict.fromkeys(label.resolved_concept for label in result.labels))
            projections[result.paragraph_ref] = TaggedParagraph(
                paragraph_id=paragraph.paragraph_id,
                text=paragraph.text,
                generated_tags=generated,
                tags=resolved,
                status="completed",
                chunk_id=paragraph.chunk_id,
                ordinal=paragraph.ordinal,
                heading_path=paragraph.heading_path,
                image_refs=paragraph.image_refs,
                image_captions=paragraph.image_captions,
            )
    if set(projections) != set(source_by_id):
        raise ValueError("chunk tagging results must cover every paragraph")
    return projections


def build_index_inputs(
    command: IngestionCommand,
    chunks: Sequence[IngestionSourceChunk],
    tagged_paragraphs: Mapping[str, TaggedParagraph],
) -> tuple[IndexInputRecord, ...]:
    """Project tagged source chunks into embedding-ready records.

    Paragraph persistence remains separate from this projection. Tags are
    copied into chunk metadata in deterministic paragraph order, while source
    text is kept byte-for-byte as produced by chunking.
    """
    inputs: list[IndexInputRecord] = []
    for chunk in chunks:
        _validate_chunk_scope(command, chunk)
        related = sorted(
            (
                paragraph
                for paragraph_id, paragraph in tagged_paragraphs.items()
                if paragraph.chunk_id == chunk.chunk_id
                or paragraph_id.startswith(f"{chunk.chunk_id}:")
            ),
            key=lambda paragraph: paragraph.paragraph_id,
        )
        unknown = [
            paragraph_id
            for paragraph_id in tagged_paragraphs
            if paragraph_id.startswith(f"{chunk.chunk_id}:")
            and paragraph_id not in {paragraph.paragraph_id for paragraph in related}
        ]
        if unknown:
            raise ValueError("tagged paragraph map contains an invalid paragraph projection")
        tags = tuple(dict.fromkeys(tag for paragraph in related for tag in paragraph.tags))
        metadata = dict(chunk.metadata)
        metadata["tags"] = tags
        metadata["tagged_paragraph_ids"] = tuple(paragraph.paragraph_id for paragraph in related)
        metadata["index_version"] = command.index_profile
        inputs.append(
            IndexInputRecord(
                chunk_id=chunk.chunk_id,
                document_ref=chunk.document_ref,
                source_version=chunk.source_version,
                search_text=chunk.search_text,
                embedding_profile=command.embedding_profile,
                access_scope=chunk.access_scope,
                metadata=metadata,
            )
        )
    return tuple(inputs)


def _validate_chunk_scope(command: IngestionCommand, chunk: IngestionSourceChunk) -> None:
    if chunk.document_ref != command.document_ref:
        raise ValueError("all chunks must belong to the command document")
    if chunk.source_version != command.source_version:
        raise ValueError("all chunks must match the command source version")
    if chunk.access_scope != command.access_scope:
        raise ValueError("all chunks must match the command access scope")


def _knowledge_chunk(record: ChunkIndexRecord) -> KnowledgeChunk:
    metadata = record.metadata
    heading_path_value = metadata.get("heading_path", ())
    if isinstance(heading_path_value, str):
        heading_path = (heading_path_value,)
    else:
        heading_path = tuple(heading_path_value) if isinstance(heading_path_value, (list, tuple)) else ()
    if not heading_path and isinstance(metadata.get("heading"), str):
        heading_path = (metadata["heading"],)
    tags_value = metadata.get("tags", ())
    image_refs_value = metadata.get("image_refs", ())
    return KnowledgeChunk(
        chunk_id=record.chunk_id,
        document_id=record.document_ref,
        source_version=record.source_version,
        source_ref=f"knowledge://{record.document_ref}/{record.chunk_id}",
        search_text=record.search_text,
        content_hash=hashlib.sha256(record.search_text.encode("utf-8")).hexdigest(),
        page_start=_metadata_page(metadata.get("page_start")),
        page_end=_metadata_page(metadata.get("page_end")),
        heading_path=heading_path,
        tags=tuple(tags_value) if isinstance(tags_value, (list, tuple)) else (),
        image_refs=tuple(image_refs_value) if isinstance(image_refs_value, (list, tuple)) else (),
        paragraph_count=_metadata_non_negative_int(metadata.get("paragraph_count")),
        image_count=_metadata_non_negative_int(metadata.get("image_count")),
    )


def _metadata_page(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else -1


def _metadata_non_negative_int(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0
