"""Typed facade for the Extract service's internal use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from saxophone.ingestion.models import IngestionCommand, IngestionSourceChunk
from saxophone.retrieval.question_retrieval import QuestionRequest
from saxophone.tagging.models import ParagraphBlock


class _IngestionService(Protocol):
    async def ingest_document(self, document: Any) -> Any: ...


class _TaggingService(Protocol):
    async def tag_chunks(self, chunks: Any) -> Any: ...


class _RetrievalService(Protocol):
    async def retrieve(self, request: QuestionRequest) -> Any: ...


class _AnsweringService(Protocol):
    async def answer(self, request: QuestionRequest) -> Any: ...


@dataclass(frozen=True, slots=True)
class TopicIngestionRequest:
    command: IngestionCommand
    chunks: tuple[IngestionSourceChunk, ...]
    paragraphs: tuple[ParagraphBlock, ...]
    resolution_profile: str
    sync_limit: int = 100
    ingestion_run_id: str | None = None
    source_hash: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command, IngestionCommand):
            raise ValueError("command must be an IngestionCommand")
        if any(not isinstance(item, IngestionSourceChunk) for item in self.chunks):
            raise ValueError("chunks must contain IngestionSourceChunk values")
        if any(not isinstance(item, ParagraphBlock) for item in self.paragraphs):
            raise ValueError("paragraphs must contain ParagraphBlock values")
        if not isinstance(self.resolution_profile, str) or not self.resolution_profile.strip():
            raise ValueError("resolution_profile must not be blank")


@dataclass(frozen=True, slots=True)
class TopicTaggingRequest:
    command: IngestionCommand
    chunks: tuple[IngestionSourceChunk, ...]
    paragraphs: tuple[ParagraphBlock, ...]


class DocumentIngestionFacadeAdapter:
    """Adapt the multi-argument ingestion coordinator to the facade contract."""

    def __init__(self, service: object) -> None:
        if not callable(getattr(service, "ingest_document", None)):
            raise ValueError("service must provide ingest_document")
        self._service = service

    async def ingest_document(self, request: TopicIngestionRequest) -> Any:
        if not isinstance(request, TopicIngestionRequest):
            raise ValueError("document must be a TopicIngestionRequest")
        return await self._service.ingest_document(
            request.command,
            request.chunks,
            request.paragraphs,
            resolution_profile=request.resolution_profile,
            sync_limit=request.sync_limit,
            ingestion_run_id=request.ingestion_run_id,
            source_hash=request.source_hash,
        )


class DocumentTaggingFacadeAdapter:
    """Adapt document chunk tagging to the facade's single request argument."""

    def __init__(self, service: object) -> None:
        if not callable(getattr(service, "execute", None)):
            raise ValueError("service must provide execute")
        self._service = service

    async def tag_chunks(self, request: TopicTaggingRequest) -> Any:
        if not isinstance(request, TopicTaggingRequest):
            raise ValueError("chunks must be a TopicTaggingRequest")
        return await self._service.execute(
            request.command,
            request.chunks,
            request.paragraphs,
        )


class ExtractTopicService:
    """Delegate Extract operations without copying domain or persistence logic."""

    def __init__(
        self,
        *,
        ingestion: _IngestionService,
        tagging: _TaggingService,
        retrieval: _RetrievalService,
        answering: _AnsweringService,
    ) -> None:
        self._require(ingestion, "ingestion", "ingest_document")
        self._require(tagging, "tagging", "tag_chunks")
        self._require(retrieval, "retrieval", "retrieve")
        self._require(answering, "answering", "answer")
        self._ingestion = ingestion
        self._tagging = tagging
        self._retrieval = retrieval
        self._answering = answering

    async def ingest_document(self, document: Any) -> Any:
        return await self._ingestion.ingest_document(document)

    async def tag_chunks(self, chunks: Any) -> Any:
        return await self._tagging.tag_chunks(chunks)

    async def retrieve_for_question(self, request: QuestionRequest) -> Any:
        self._validate_request(request)
        return await self._retrieval.retrieve(request)

    async def answer_question(self, request: QuestionRequest) -> Any:
        self._validate_request(request)
        return await self._answering.answer(request)

    @staticmethod
    def _validate_request(request: QuestionRequest) -> None:
        if not isinstance(request, QuestionRequest):
            raise ValueError("request must be a QuestionRequest")

    @staticmethod
    def _require(service: object, name: str, method: str) -> None:
        if not callable(getattr(service, method, None)):
            raise ValueError(f"{name} must provide {method}")
