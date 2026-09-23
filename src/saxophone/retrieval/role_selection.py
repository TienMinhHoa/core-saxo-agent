"""Validated concept-role selection contracts and remote adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from saxophone.platform.model_client import ModelClient, ModelRequest, ModelTask, ModelValidationError
from saxophone.tagging.models import ContentRole
from saxophone.tagging.structured_provider import StructuredLlmProvider


@dataclass(frozen=True, slots=True)
class ConceptRoleCandidate:
    canonical_concept: str
    available_roles: tuple[ContentRole, ...]
    chunk_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text("canonical_concept", self.canonical_concept)
        roles = _roles(self.available_roles)
        refs = _texts(self.chunk_refs, "chunk_refs")
        if not roles:
            raise ValueError("available_roles must not be empty")
        if len(set(refs)) != len(refs):
            raise ValueError("chunk_refs must not contain duplicates")
        object.__setattr__(self, "canonical_concept", self.canonical_concept.strip())
        object.__setattr__(self, "available_roles", roles)
        object.__setattr__(self, "chunk_refs", refs)


@dataclass(frozen=True, slots=True)
class ConceptRoleSelectionRequest:
    question: str
    candidates: tuple[ConceptRoleCandidate, ...]

    def __post_init__(self) -> None:
        _text("question", self.question)
        if not self.candidates:
            raise ValueError("candidates must not be empty")
        if any(not isinstance(item, ConceptRoleCandidate) for item in self.candidates):
            raise ValueError("candidates must contain ConceptRoleCandidate values")
        concepts = tuple(item.canonical_concept for item in self.candidates)
        if len(set(concepts)) != len(concepts):
            raise ValueError("candidates must not contain duplicate concepts")
        object.__setattr__(self, "question", self.question.strip())
        object.__setattr__(self, "candidates", tuple(self.candidates))


@dataclass(frozen=True, slots=True)
class ConceptRoleSelection:
    concept: str
    selected_roles: tuple[ContentRole, ...]
    selection_rank: int

    def __post_init__(self) -> None:
        _text("concept", self.concept)
        roles = _roles(self.selected_roles)
        if not roles:
            raise ValueError("selected_roles must not be empty")
        if isinstance(self.selection_rank, bool) or not isinstance(self.selection_rank, int) or self.selection_rank < 1:
            raise ValueError("selection_rank must be a positive integer")
        object.__setattr__(self, "concept", self.concept.strip())
        object.__setattr__(self, "selected_roles", roles)


@dataclass(frozen=True, slots=True)
class ConceptRoleSelectionResult:
    selections: tuple[ConceptRoleSelection, ...]

    def __post_init__(self) -> None:
        if any(not isinstance(item, ConceptRoleSelection) for item in self.selections):
            raise ValueError("selections must contain ConceptRoleSelection values")
        concepts = tuple(item.concept for item in self.selections)
        if len(set(concepts)) != len(concepts):
            raise ValueError("selections must not contain duplicate concepts")
        ranks = tuple(item.selection_rank for item in self.selections)
        if len(set(ranks)) != len(ranks):
            raise ValueError("selection_rank values must be unique")
        object.__setattr__(self, "selections", tuple(self.selections))

    def validate_against(self, request: ConceptRoleSelectionRequest) -> None:
        candidates = {item.canonical_concept: item for item in request.candidates}
        for selection in self.selections:
            candidate = candidates.get(selection.concept)
            if candidate is None:
                raise ValueError("selection concept must be present in candidates")
            if any(role not in candidate.available_roles for role in selection.selected_roles):
                raise ValueError("selection role must be available for the concept")


class ConceptRoleSelector(Protocol):
    async def select(self, request: ConceptRoleSelectionRequest) -> ConceptRoleSelectionResult:
        ...


@dataclass(frozen=True, slots=True)
class _StructuredSelection:
    concept: str
    selected_roles: tuple[ContentRole, ...]
    selection_rank: int


@dataclass(frozen=True, slots=True)
class _StructuredSelectionResult:
    selections: tuple[_StructuredSelection, ...]

    @classmethod
    def model_json_schema(cls) -> dict[str, object]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["selections"],
            "properties": {
                "selections": {"type": "array", "items": {"type": "object"}},
            },
        }

    @classmethod
    def model_validate(cls, value: object) -> "_StructuredSelectionResult":
        if not isinstance(value, Mapping) or set(value) != {"selections"}:
            raise ValueError("role selection output fields do not match the contract")
        raw_selections = value.get("selections")
        if not isinstance(raw_selections, list):
            raise ValueError("selections must be a list")
        selections: list[_StructuredSelection] = []
        for raw in raw_selections:
            if not isinstance(raw, Mapping) or set(raw) != {
                "concept",
                "selected_roles",
                "selection_rank",
            }:
                raise ValueError("selection fields do not match the contract")
            concept = raw.get("concept")
            roles = raw.get("selected_roles")
            rank = raw.get("selection_rank")
            if not isinstance(concept, str) or not concept.strip():
                raise ValueError("selection concept must not be blank")
            if not isinstance(roles, list):
                raise ValueError("selected_roles must be a list")
            if isinstance(rank, bool) or not isinstance(rank, int):
                raise ValueError("selection_rank must be an integer")
            selections.append(
                _StructuredSelection(
                    concept.strip(),
                    tuple(ContentRole(role) for role in roles),
                    rank,
                )
            )
        return cls(tuple(selections))


class StructuredConceptRoleSelector:
    """Select only candidate concept-role pairs through the shared provider."""

    def __init__(self, provider: StructuredLlmProvider) -> None:
        if not callable(getattr(provider, "generate_structured", None)):
            raise TypeError("provider must provide generate_structured")
        self._provider = provider

    async def select(
        self,
        request: ConceptRoleSelectionRequest,
    ) -> ConceptRoleSelectionResult:
        if not isinstance(request, ConceptRoleSelectionRequest):
            raise ValueError("request must be a ConceptRoleSelectionRequest")
        payload = await self._provider.generate_structured(
            task_type="concept_role_selection",
            system_prompt=(
                "Select only relevant concepts and roles from the supplied candidate list. "
                "Never invent a concept or role."
            ),
            user_prompt=_selection_markdown(request),
            response_model=_StructuredSelectionResult,
        )
        result = ConceptRoleSelectionResult(
            tuple(
                ConceptRoleSelection(
                    item.concept,
                    tuple(item.selected_roles),
                    item.selection_rank,
                )
                for item in payload.selections
            )
        )
        result.validate_against(request)
        return result


class RemoteConceptRoleSelector:
    """Map one role-selection request to one validated retrieval model call."""

    def __init__(self, client: ModelClient, *, model: str, response_schema: str = "concept-role-selection-v1") -> None:
        _text("model", model)
        _text("response_schema", response_schema)
        self._client = client
        self._model = model.strip()
        self._response_schema = response_schema.strip()

    async def select(self, request: ConceptRoleSelectionRequest) -> ConceptRoleSelectionResult:
        response = await self._client.invoke(ModelRequest(
            model=self._model,
            task=ModelTask.RETRIEVAL_SELECT,
            input={
                "question": request.question,
                "candidates": [
                    {
                        "concept": item.canonical_concept,
                        "available_roles": [role.value for role in item.available_roles],
                        "chunk_refs": list(item.chunk_refs),
                    }
                    for item in request.candidates
                ],
            },
            metadata={"selection_profile": "concept-role"},
            response_schema=self._response_schema,
            idempotency_key=f"role-select-{request.question}",
        ))
        if response.task is not ModelTask.RETRIEVAL_SELECT or response.response_schema != self._response_schema:
            raise ModelValidationError("model response does not match role-selection contract")
        raw = response.output.get("selections")
        if not isinstance(raw, list):
            raise ModelValidationError("selections must be a list")
        selections: list[ConceptRoleSelection] = []
        for item in raw:
            if not isinstance(item, dict):
                raise ModelValidationError("selection must be a mapping")
            roles = item.get("selected_roles")
            if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
                raise ModelValidationError("selected_roles must be a list of strings")
            try:
                selections.append(ConceptRoleSelection(item.get("concept", ""), tuple(roles), item.get("selection_rank", 0)))
            except ValueError as exc:
                raise ModelValidationError(str(exc)) from exc
        try:
            result = ConceptRoleSelectionResult(tuple(selections))
            result.validate_against(request)
            return result
        except ValueError as exc:
            raise ModelValidationError(str(exc)) from exc


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")


def _texts(values: tuple[str, ...], name: str) -> tuple[str, ...]:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{name} must contain non-blank strings")
    return tuple(value.strip() for value in values)


def _roles(values: tuple[ContentRole, ...]) -> tuple[ContentRole, ...]:
    try:
        roles = tuple(value if isinstance(value, ContentRole) else ContentRole(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError("roles must contain supported content roles") from exc
    if len(set(roles)) != len(roles):
        raise ValueError("roles must not contain duplicates")
    return roles


def _selection_markdown(request: ConceptRoleSelectionRequest) -> str:
    lines = [
        "# Concept and Role Selection",
        "",
        "## User question",
        "",
        request.question,
        "",
        "## Candidate concepts from retrieved chunks",
        "",
    ]
    for candidate in request.candidates:
        lines.extend((f"### Concept: {candidate.canonical_concept}", ""))
        lines.extend(
            f"- Available role: {role.value}"
            for role in candidate.available_roles
        )
        if candidate.chunk_refs:
            lines.append(f"- Parent chunks: {', '.join(candidate.chunk_refs)}")
        lines.append("")
    return "\n".join(lines).strip()
