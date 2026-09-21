from dataclasses import dataclass

import pytest

from saxophone.platform.model_client import ModelRequest, ModelResponse, ModelTask, ModelValidationError
from saxophone.retrieval.role_selection import (
    ConceptRoleCandidate,
    ConceptRoleSelectionRequest,
    RemoteConceptRoleSelector,
)
from saxophone.tagging.models import ContentRole


@dataclass
class FakeClient:
    response: ModelResponse
    requests: list[ModelRequest] | None = None

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        self.requests = (self.requests or []) + [request]
        return self.response


def _request() -> ConceptRoleSelectionRequest:
    return ConceptRoleSelectionRequest(
        "What is harmony?",
        (ConceptRoleCandidate("Harmony", (ContentRole.DEFINITION, ContentRole.EXAMPLE), ("chunk-1",)),),
    )


@pytest.mark.anyio
async def test_role_selector_maps_and_validates_available_roles() -> None:
    response = ModelResponse(
        ModelTask.RETRIEVAL_SELECT,
        "selector",
        "concept-role-selection-v1",
        {"selections": [{"concept": "Harmony", "selected_roles": ["Definition"], "selection_rank": 1}]},
        "v1",
    )
    client = FakeClient(response)
    result = await RemoteConceptRoleSelector(client, model="selector").select(_request())
    assert result.selections[0].selected_roles == (ContentRole.DEFINITION,)
    assert client.requests[0].input["candidates"][0]["chunk_refs"] == ["chunk-1"]


@pytest.mark.anyio
async def test_role_selector_rejects_foreign_role() -> None:
    response = ModelResponse(
        ModelTask.RETRIEVAL_SELECT,
        "selector",
        "concept-role-selection-v1",
        {"selections": [{"concept": "Harmony", "selected_roles": ["Procedure"], "selection_rank": 1}]},
        "v1",
    )
    with pytest.raises(ModelValidationError, match="available"):
        await RemoteConceptRoleSelector(FakeClient(response), model="selector").select(_request())


def test_role_selection_request_rejects_duplicate_concepts() -> None:
    candidate = ConceptRoleCandidate("Harmony", (ContentRole.DEFINITION,))
    with pytest.raises(ValueError, match="duplicate concepts"):
        ConceptRoleSelectionRequest("question", (candidate, candidate))
