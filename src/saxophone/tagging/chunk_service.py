"""Application service for one validated concept-role tagging call per chunk."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from saxophone.documents.policies import is_safe_document_reference

from .chunk_models import ChunkTaggingRequest, ChunkTaggingResult
from .models import ParagraphConceptRole
from .ports import ChunkTagger
from .vector_outbox import VectorOutboxEvent


@dataclass(frozen=True, slots=True)
class ChunkTaggingRun:
    """A validated provider result and its relational source-of-truth projection."""

    result: ChunkTaggingResult
    relations: tuple[ParagraphConceptRole, ...]


class _ChunkRelationRepository(Protocol):
    async def replace_chunk_relations(
        self,
        document_ref: str,
        source_version: str,
        paragraph_ids: tuple[str, ...],
        relations: tuple[ParagraphConceptRole, ...],
    ) -> None: ...


class ChunkTaggingService:
    """Run exactly one tagger call and project validated paragraph-concept roles."""

    def __init__(self, tagger: ChunkTagger) -> None:
        if not callable(getattr(tagger, "tag", None)):
            raise TypeError("tagger must provide tag")
        self._tagger = tagger

    async def tag_chunk(self, request: ChunkTaggingRequest) -> ChunkTaggingRun:
        if not isinstance(request, ChunkTaggingRequest):
            raise TypeError("request must be a ChunkTaggingRequest")
        result = await self._tagger.tag(request)
        if not isinstance(result, ChunkTaggingResult):
            raise TypeError("tagger must return ChunkTaggingResult")
        result.validate_against(request)
        relations = tuple(
            ParagraphConceptRole(paragraph.paragraph_ref, label.resolved_concept, role)
            for paragraph in result.paragraphs
            for label in paragraph.labels
            for role in label.roles
        )
        return ChunkTaggingRun(result=result, relations=relations)


class _ChunkTransactionRepository(Protocol):
    async def commit_chunk(
        self,
        *,
        document_ref: str,
        source_version: str,
        paragraph_ids: Sequence[str],
        relations: Sequence[ParagraphConceptRole],
        outbox_events: Sequence[VectorOutboxEvent],
    ) -> None: ...


class _DocumentTransactionRepository(Protocol):
    async def commit_document(
        self,
        *,
        document_ref: str,
        source_version: str,
        paragraph_ids: Sequence[str],
        relations: Sequence[ParagraphConceptRole],
        outbox_events: Sequence[VectorOutboxEvent],
        previous_source_versions: Sequence[str],
    ) -> None: ...


class ChunkTaggingTransactionService:
    """Commit one validated chunk result with its vector work atomically."""

    def __init__(
        self,
        tagging_service: ChunkTaggingService,
        transaction_repository: _ChunkTransactionRepository,
    ) -> None:
        if not isinstance(tagging_service, ChunkTaggingService):
            raise TypeError("tagging_service must be a ChunkTaggingService")
        if not callable(getattr(transaction_repository, "commit_chunk", None)):
            raise TypeError("transaction_repository must provide commit_chunk")
        self._tagging_service = tagging_service
        self._transaction_repository = transaction_repository

    async def tag(self, request: ChunkTaggingRequest) -> ChunkTaggingRun:
        """Prepare one validated chunk result without changing durable state."""

        if not isinstance(request, ChunkTaggingRequest):
            raise TypeError("request must be a ChunkTaggingRequest")
        return await self._tagging_service.tag_chunk(request)

    async def commit(
        self,
        document_ref: str,
        source_version: str,
        request: ChunkTaggingRequest,
        run: ChunkTaggingRun,
        *,
        outbox_events: Sequence[VectorOutboxEvent] = (),
    ) -> None:
        """Atomically persist a prepared result and its vector events."""

        _validate_commit_scope(document_ref, source_version)
        if not isinstance(request, ChunkTaggingRequest):
            raise TypeError("request must be a ChunkTaggingRequest")
        if not isinstance(run, ChunkTaggingRun):
            raise TypeError("run must be a ChunkTaggingRun")
        run.result.validate_against(request)
        normalized_events = _validate_outbox_events(outbox_events)
        await self._transaction_repository.commit_chunk(
            document_ref=document_ref,
            source_version=source_version,
            paragraph_ids=tuple(item.paragraph.paragraph_id for item in request.paragraphs),
            relations=run.relations,
            outbox_events=normalized_events,
        )

    async def commit_document(
        self,
        document_ref: str,
        source_version: str,
        requests: Sequence[ChunkTaggingRequest],
        runs: Sequence[ChunkTaggingRun],
        *,
        outbox_events: Sequence[VectorOutboxEvent] = (),
        previous_source_versions: Sequence[str] = (),
    ) -> None:
        """Atomically persist all prepared chunk results for one document."""

        _validate_commit_scope(document_ref, source_version)
        repository = self._transaction_repository
        if not callable(getattr(repository, "commit_document", None)):
            raise TypeError("transaction_repository must provide commit_document")
        if isinstance(requests, (str, bytes)) or not isinstance(requests, Sequence):
            raise TypeError("requests must be a sequence")
        if isinstance(runs, (str, bytes)) or not isinstance(runs, Sequence):
            raise TypeError("runs must be a sequence")
        normalized_requests = tuple(requests)
        normalized_runs = tuple(runs)
        if len(normalized_requests) != len(normalized_runs):
            raise ValueError("requests and runs must have matching lengths")

        paragraph_ids: list[str] = []
        relations: list[ParagraphConceptRole] = []
        for request, run in zip(normalized_requests, normalized_runs):
            if not isinstance(request, ChunkTaggingRequest):
                raise TypeError("requests must contain ChunkTaggingRequest values")
            if not isinstance(run, ChunkTaggingRun):
                raise TypeError("runs must contain ChunkTaggingRun values")
            run.result.validate_against(request)
            paragraph_ids.extend(item.paragraph.paragraph_id for item in request.paragraphs)
            relations.extend(run.relations)

        normalized_paragraph_ids = tuple(paragraph_ids)
        if len(normalized_paragraph_ids) != len(set(normalized_paragraph_ids)):
            raise ValueError("document tagging requests must not repeat paragraph references")
        relation_keys = tuple(
            (item.paragraph_id, item.canonical_concept, item.content_role.value)
            for item in relations
        )
        if len(relation_keys) != len(set(relation_keys)):
            raise ValueError("document tagging relations must be unique")
        if any(item.paragraph_id not in set(normalized_paragraph_ids) for item in relations):
            raise ValueError("document tagging relations must belong to requests")

        normalized_events = _validate_outbox_events(outbox_events)
        normalized_previous_versions = _validate_previous_source_versions(
            source_version,
            previous_source_versions,
        )
        await repository.commit_document(
            document_ref=document_ref,
            source_version=source_version,
            paragraph_ids=normalized_paragraph_ids,
            relations=tuple(relations),
            outbox_events=normalized_events,
            previous_source_versions=normalized_previous_versions,
        )

    async def tag_and_commit(
        self,
        document_ref: str,
        source_version: str,
        request: ChunkTaggingRequest,
        *,
        outbox_events: Sequence[VectorOutboxEvent] = (),
    ) -> ChunkTaggingRun:
        _validate_commit_scope(document_ref, source_version)
        run = await self.tag(request)
        await self.commit(
            document_ref,
            source_version,
            request,
            run,
            outbox_events=outbox_events,
        )
        return run


class ChunkTaggingPersistenceService:
    """Commit one validated chunk tagging run without replacing sibling chunks."""

    def __init__(
        self,
        tagging_service: ChunkTaggingService,
        repository: _ChunkRelationRepository,
    ) -> None:
        if not isinstance(tagging_service, ChunkTaggingService):
            raise TypeError("tagging_service must be a ChunkTaggingService")
        if not callable(getattr(repository, "replace_chunk_relations", None)):
            raise TypeError("repository must provide replace_chunk_relations")
        self._tagging_service = tagging_service
        self._repository = repository

    async def tag_and_persist(
        self,
        document_ref: str,
        source_version: str,
        request: ChunkTaggingRequest,
    ) -> ChunkTaggingRun:
        run = await self._tagging_service.tag_chunk(request)
        await self._repository.replace_chunk_relations(
            document_ref,
            source_version,
            tuple(item.paragraph.paragraph_id for item in request.paragraphs),
            run.relations,
        )
        return run


def _validate_commit_scope(document_ref: str, source_version: str) -> None:
    if not isinstance(document_ref, str) or not document_ref.strip():
        raise ValueError("document_ref must not be blank")
    if not is_safe_document_reference(document_ref):
        raise ValueError("document_ref must be a safe document reference")
    if not isinstance(source_version, str) or not source_version.strip():
        raise ValueError("source_version must not be blank")


def _validate_outbox_events(
    outbox_events: Sequence[VectorOutboxEvent],
) -> tuple[VectorOutboxEvent, ...]:
    if isinstance(outbox_events, (str, bytes)) or not isinstance(outbox_events, Sequence):
        raise TypeError("outbox_events must be a sequence")
    normalized_events = tuple(outbox_events)
    if any(not isinstance(event, VectorOutboxEvent) for event in normalized_events):
        raise TypeError("outbox_events must contain VectorOutboxEvent values")
    if len({event.event_id for event in normalized_events}) != len(normalized_events):
        raise ValueError("outbox_events must not contain duplicate event IDs")
    return normalized_events


def _validate_previous_source_versions(
    source_version: str,
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
    if source_version in normalized:
        raise ValueError("previous_source_versions must not contain the new source version")
    return normalized
