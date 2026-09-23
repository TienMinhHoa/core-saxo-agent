from __future__ import annotations

import json
from pathlib import Path

import pytest

from saxophone.app.factory import AppOverrides, create_app
from saxophone.app.settings import AppSettings
from saxophone.chat.service import GroundedAnswerStatus
from saxophone.ingestion.adapters import FakeEmbeddingProvider, FakeVectorIndex
from saxophone.ingestion.chunking import build_source_chunks
from saxophone.ingestion.models import IngestionCommand
from saxophone.retrieval.question_retrieval import QuestionRequest
from saxophone.services.extract_topic import (
    TopicIngestionRequest,
)
from saxophone.tagging.parser import parse_chunk_paragraphs
from saxophone.tagging.structured_provider import FakeStructuredLlmProvider


class _RemoteGpu:
    async def health(self):
        raise AssertionError("end-to-end test must not call the remote GPU gateway")


class _ModelClient:
    async def invoke(self, request):
        raise AssertionError("structured and embedding fakes must own provider calls")


def _fixture_markdown() -> str:
    fixture = Path("tests/fixtures/golden/chroma_sidecar/header_chunks.json")
    chunks = json.loads(fixture.read_text(encoding="utf-8"))
    return "\n\n".join(
        f"## {chunk['header']}\n\n{chunk['content']}" for chunk in chunks
    )


@pytest.mark.anyio
async def test_existing_document_fixture_can_be_ingested_tagged_and_answered(tmp_path: Path) -> None:
    markdown = _fixture_markdown()
    chunks = build_source_chunks(
        markdown,
        document_ref="existing-music-document",
        source_version="source-v1",
        access_scope="offline-test",
    )
    paragraphs = tuple(
        paragraph for chunk in chunks for paragraph in parse_chunk_paragraphs(chunk)
    )
    assert chunks and paragraphs

    tagging_paragraphs = []
    for index, _paragraph in enumerate(paragraphs):
        tagging_paragraphs.append(
            {
                "paragraph_ref": f"p{index + 1}",
                "labels": [
                    {
                        "generated_concept": "Rhythm",
                        "action": "create_new" if index == 0 else "reuse_chunk_new",
                        "resolved_concept": "Rhythm",
                        "roles": ["Definition"],
                    }
                ],
                "tagging_status": "completed",
            }
        )
    used_ref = paragraphs[0].paragraph_id
    structured = FakeStructuredLlmProvider(
        {
            "chunk_tagging_and_conflict": {
                "chunk_id": chunks[0].chunk_id,
                "chunk_new_concepts": ["Rhythm"],
                "paragraphs": tagging_paragraphs,
            },
            "concept_role_selection": {
                "selections": [
                    {
                        "concept": "Rhythm",
                        "selected_roles": ["Definition"],
                        "selection_rank": 1,
                    }
                ]
            },
            "answer_generation": {
                "answer": "Rhythm keeps the musical pulse organized.",
                "used_paragraph_refs": [used_ref],
            },
        }
    )
    embeddings = FakeEmbeddingProvider(
        {chunks[0].chunk_id: (1.0, 0.0)},
        text_vectors={"What is rhythm?": (1.0, 0.0)},
        default_text_vector=(1.0, 0.0),
    )
    vectors = FakeVectorIndex()
    command = IngestionCommand(
        document_ref="existing-music-document",
        source_version="source-v1",
        chunking_profile="header-v1",
        tagging_profile="topic-v1",
        embedding_profile="fake-embedding",
        index_profile="topic-index-v1",
        access_scope="offline-test",
    )
    settings = AppSettings.from_environment(
        {
            "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
            "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
            "SAXO_DATA_ROOT": str(tmp_path),
            "SAXO_CHUNK_TAGGING_ENABLED": "true",
        }
    )
    app = create_app(
        settings,
        overrides=AppOverrides(
            remote_gpu_gateway=_RemoteGpu(),
            model_client=_ModelClient(),
            embedding_provider=embeddings,
            vector_index=vectors,
            structured_llm_provider=structured,
        ),
    )
    facade = app.state.container.extract_topic
    assert facade is not None

    report = await facade.ingest_document(
        TopicIngestionRequest(
            command=command,
            chunks=chunks,
            paragraphs=paragraphs,
            resolution_profile="topic-v1",
            ingestion_run_id="run-existing-fixture",
            source_hash="fixture-source-hash",
        )
    )
    answer = await facade.answer_question(QuestionRequest("What is rhythm?"))

    assert report.indexed is True
    assert vectors.chunk_records
    assert vectors.concept_records
    assert answer.status is GroundedAnswerStatus.ANSWERED
    assert answer.sources[0].paragraph_ref == used_ref
    assert answer.sources[0].chunk_id == chunks[0].chunk_id
