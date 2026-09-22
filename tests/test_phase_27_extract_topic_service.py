from __future__ import annotations

import asyncio

import pytest

from saxophone.retrieval.question_retrieval import QuestionRequest
from saxophone.services.extract_topic import ExtractTopicService


class _Ingest:
    def __init__(self) -> None:
        self.documents: list[object] = []

    async def ingest_document(self, document: object) -> str:
        self.documents.append(document)
        return "ingested"


class _Tag:
    def __init__(self) -> None:
        self.chunks: list[object] = []

    async def tag_chunks(self, chunks: object) -> str:
        self.chunks.append(chunks)
        return "tagged"


class _Retrieval:
    async def retrieve(self, request: QuestionRequest) -> str:
        return f"retrieved:{request.question}"


class _Answer:
    async def answer(self, request: QuestionRequest) -> str:
        return f"answered:{request.question}"


def test_extract_topic_service_delegates_each_internal_boundary() -> None:
    ingestion = _Ingest()
    tagging = _Tag()
    retrieval = _Retrieval()
    answer = _Answer()
    service = ExtractTopicService(
        ingestion=ingestion,
        tagging=tagging,
        retrieval=retrieval,
        answering=answer,
    )
    request = QuestionRequest("What is harmony?")

    async def run() -> tuple[object, ...]:
        return (
            await service.ingest_document("document"),
            await service.tag_chunks("chunks"),
            await service.retrieve_for_question(request),
            await service.answer_question(request),
        )

    assert asyncio.run(run()) == (
        "ingested",
        "tagged",
        "retrieved:What is harmony?",
        "answered:What is harmony?",
    )
    assert ingestion.documents == ["document"]
    assert tagging.chunks == ["chunks"]


def test_extract_topic_service_rejects_invalid_question_request() -> None:
    service = ExtractTopicService(
        ingestion=_Ingest(),
        tagging=_Tag(),
        retrieval=_Retrieval(),
        answering=_Answer(),
    )

    with pytest.raises(ValueError, match="request must be a QuestionRequest"):
        asyncio.run(service.retrieve_for_question("question"))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="request must be a QuestionRequest"):
        asyncio.run(service.answer_question("question"))  # type: ignore[arg-type]


def test_extract_topic_service_requires_all_collaborators() -> None:
    with pytest.raises(ValueError, match="ingestion must provide ingest_document"):
        ExtractTopicService(
            ingestion=object(),
            tagging=_Tag(),
            retrieval=_Retrieval(),
            answering=_Answer(),
        )
