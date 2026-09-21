from __future__ import annotations

import pytest

from saxophone.tagging.chunk_models import (
    ChunkParagraphTaggingInput,
    ChunkParagraphTaggingResult,
    ChunkTaggingLabel,
    ChunkTaggingRequest,
    ChunkTaggingResult,
)
import asyncio

from saxophone.platform.model_client import ModelResponse, ModelTask
from saxophone.tagging.adapters import RemoteChunkTagger
from saxophone.tagging.models import ContentRole, ParagraphBlock


def _request() -> ChunkTaggingRequest:
    first = ParagraphBlock("p-1", "chunk-1", 0, "A major triad has three notes.")
    second = ParagraphBlock("p-2", "chunk-1", 1, "Stack a third then a fifth.")
    return ChunkTaggingRequest(
        chunk_id="chunk-1",
        paragraphs=(
            ChunkParagraphTaggingInput(first, existing_candidates=("Major triad",)),
            ChunkParagraphTaggingInput(second, existing_candidates=("Major triad",)),
        ),
    )


def _result() -> ChunkTaggingResult:
    return ChunkTaggingResult(
        chunk_id="chunk-1",
        chunk_new_concepts=("Chord construction",),
        paragraphs=(
            ChunkParagraphTaggingResult(
                "p-1",
                (
                    ChunkTaggingLabel(
                        "Major chord",
                        "reuse_existing",
                        "Major triad",
                        (ContentRole.DEFINITION,),
                    ),
                ),
            ),
            ChunkParagraphTaggingResult(
                "p-2",
                (
                    ChunkTaggingLabel(
                        "Building a chord",
                        "create_new",
                        "Chord construction",
                        (ContentRole.PROCEDURE,),
                    ),
                ),
            ),
        ),
    )


def test_chunk_tagging_result_validates_every_requested_paragraph_and_concept_action() -> None:
    result = _result()

    result.validate_against(_request())

    assert result.paragraphs[0].labels[0].roles == (ContentRole.DEFINITION,)


@pytest.mark.parametrize(
    ("action", "resolved_concept", "message"),
    [
        ("reuse_existing", "Chord construction", "existing candidate"),
        ("create_new", "Major triad", "chunk_new_concepts"),
        ("reuse_chunk_new", "Major triad", "chunk_new_concepts"),
    ],
)
def test_chunk_tagging_rejects_invalid_action_provenance(
    action: str, resolved_concept: str, message: str
) -> None:
    result = _result()
    invalid_label = ChunkTaggingLabel(
        "Major chord", action, resolved_concept, (ContentRole.DEFINITION,)
    )
    invalid_paragraph = ChunkParagraphTaggingResult("p-1", (invalid_label,))
    result = ChunkTaggingResult(
        result.chunk_id,
        result.chunk_new_concepts,
        (invalid_paragraph, result.paragraphs[1]),
    )

    with pytest.raises(ValueError, match=message):
        result.validate_against(_request())


def test_chunk_tagging_rejects_unknown_or_missing_paragraph_refs() -> None:
    result = _result()
    unknown = ChunkParagraphTaggingResult("p-3", result.paragraphs[1].labels)
    invalid = ChunkTaggingResult(result.chunk_id, result.chunk_new_concepts, (result.paragraphs[0], unknown))

    with pytest.raises(ValueError, match="paragraph refs"):
        invalid.validate_against(_request())


def test_chunk_tagging_label_requires_at_least_one_valid_role() -> None:
    with pytest.raises(ValueError, match="roles"):
        ChunkTaggingLabel("Major chord", "reuse_existing", "Major triad", ())

    with pytest.raises(ValueError, match="roles"):
        ChunkTaggingLabel("Major chord", "reuse_existing", "Major triad", ("Unknown",))


class _FakeClient:
    def __init__(self, response: ModelResponse) -> None:
        self.response = response
        self.requests = []

    async def invoke(self, request):
        self.requests.append(request)
        return self.response


def test_remote_chunk_tagger_maps_one_validated_chunk_call() -> None:
    request = _request()
    response = ModelResponse(
        task=ModelTask.CHUNK_TAGGING,
        model="deepseek-test",
        response_schema="chunk-tagging-v1",
        source_version="fixture",
        output={
            "chunk_id": "chunk-1",
            "chunk_new_concepts": ["Chord construction"],
            "paragraphs": [
                {"paragraph_ref": "p-1", "labels": [{"generated_concept": "Major chord", "action": "reuse_existing", "resolved_concept": "Major triad", "roles": ["Definition"]}]},
                {"paragraph_ref": "p-2", "labels": [{"generated_concept": "Building a chord", "action": "create_new", "resolved_concept": "Chord construction", "roles": ["Procedure"]}]},
            ],
        },
    )
    client = _FakeClient(response)
    result = asyncio.run(RemoteChunkTagger(client, model="deepseek-test").tag(request))

    result.validate_against(request)
    assert client.requests[0].task is ModelTask.CHUNK_TAGGING
    assert client.requests[0].input["chunk_id"] == "chunk-1"


def test_remote_chunk_tagger_rejects_foreign_response_refs() -> None:
    request = _request()
    response = ModelResponse(
        task=ModelTask.CHUNK_TAGGING,
        model="deepseek-test",
        response_schema="chunk-tagging-v1",
        source_version="fixture",
        output={
            "chunk_id": "chunk-1",
            "chunk_new_concepts": [],
            "paragraphs": [{"paragraph_ref": "p-foreign", "labels": []}, {"paragraph_ref": "p-2", "labels": []}],
        },
    )
    client = _FakeClient(response)

    with pytest.raises(ValueError, match="paragraph refs"):
        asyncio.run(RemoteChunkTagger(client, model="deepseek-test").tag(request))
