from dataclasses import dataclass

import pytest

from saxophone.platform.model_client import ModelRequest, ModelResponse, ModelTask, ModelValidationError
from saxophone.tagging.adapters import RemoteParagraphTagger, RemoteTagConflictResolver
from saxophone.tagging.models import ExistingTagCandidate, ParagraphBlock, TagConflictResolutionRequest, TagGenerationRequest


@dataclass
class FakeModelClient:
    response: ModelResponse
    requests: list[ModelRequest] | None = None

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        if self.requests is None:
            self.requests = []
        self.requests.append(request)
        return self.response


def _paragraph() -> ParagraphBlock:
    return ParagraphBlock("p-1", "c-1", 0, "Harmony is the combination of sounds.", ("Music",))


@pytest.mark.anyio
async def test_remote_paragraph_tagger_maps_typed_request_and_output() -> None:
    client = FakeModelClient(ModelResponse(ModelTask.PARAGRAPH_TAG, "tagger", "paragraph-tags-v1", {"paragraph_id": "p-1", "tags": ["Harmony definition"]}, "v1"))
    result = await RemoteParagraphTagger(client, model="tagger").generate(TagGenerationRequest(_paragraph(), "tags-v1"))
    assert result.tags == ("Harmony definition",)
    assert client.requests[0].input["text"] == _paragraph().text


@pytest.mark.anyio
async def test_remote_conflict_resolver_maps_resolutions_and_candidates() -> None:
    response = ModelResponse(ModelTask.TAG_RESOLVE, "resolver", "tag-resolution-v1", {"paragraph_id": "p-1", "resolutions": [{"generated_tag": "Harmony", "action": "reuse_existing", "resolved_tag": "Harmony definition"}]}, "v1")
    client = FakeModelClient(response)
    request = TagConflictResolutionRequest("p-1", ("Harmony",), (ExistingTagCandidate("Harmony definition"),), "resolve-v1")
    result = await RemoteTagConflictResolver(client, model="resolver").resolve(request)
    assert result.resolutions[0].resolved_tag == "Harmony definition"
    assert client.requests[0].input["existing_tags"][0]["tag"] == "Harmony definition"


@pytest.mark.anyio
async def test_remote_tagging_rejects_wrong_task_before_mapping() -> None:
    response = ModelResponse(ModelTask.EMBED, "tagger", "paragraph-tags-v1", {"paragraph_id": "p-1", "tags": []}, "v1")
    with pytest.raises(ModelValidationError, match="task"):
        await RemoteParagraphTagger(FakeModelClient(response), model="tagger").generate(TagGenerationRequest(_paragraph(), "tags-v1"))


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("resolution", "message"),
    [
        ({"generated_tag": "Harmony", "action": "unknown", "resolved_tag": "Harmony"}, "action"),
        ({"generated_tag": "", "action": "keep_new", "resolved_tag": "Harmony"}, "generated_tag"),
        ({"generated_tag": "Harmony", "action": "keep_new", "resolved_tag": ""}, "resolved_tag"),
    ],
)
async def test_remote_conflict_resolver_wraps_invalid_resolution_as_model_validation_error(
    resolution: dict[str, str], message: str
) -> None:
    response = ModelResponse(
        ModelTask.TAG_RESOLVE,
        "resolver",
        "tag-resolution-v1",
        {"paragraph_id": "p-1", "resolutions": [resolution]},
        "v1",
    )
    request = TagConflictResolutionRequest(
        "p-1", ("Harmony",), (ExistingTagCandidate("Harmony definition"),), "resolve-v1"
    )

    with pytest.raises(ModelValidationError, match=message):
        await RemoteTagConflictResolver(FakeModelClient(response), model="resolver").resolve(request)
