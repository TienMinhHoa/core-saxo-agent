"""Typed facade for the Extract service's internal use cases."""

from __future__ import annotations

from typing import Any, Protocol

from saxophone.retrieval.question_retrieval import QuestionRequest


class _IngestionService(Protocol):
    async def ingest_document(self, document: Any) -> Any: ...


class _TaggingService(Protocol):
    async def tag_chunks(self, chunks: Any) -> Any: ...


class _RetrievalService(Protocol):
    async def retrieve(self, request: QuestionRequest) -> Any: ...


class _AnsweringService(Protocol):
    async def answer(self, request: QuestionRequest) -> Any: ...


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
