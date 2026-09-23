"""Structured-provider adapter for one-call chunk tagging and conflict resolution."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from .chunk_models import (
    ChunkParagraphTaggingResult,
    ChunkTaggingLabel,
    ChunkTaggingRequest,
    ChunkTaggingResult,
)
from .models import ContentRole
from .ports import ChunkTagger
from .structured_provider import StructuredLlmProvider


@dataclass(frozen=True, slots=True)
class _StructuredLabel:
    generated_concept: str
    action: str
    resolved_concept: str
    roles: tuple[ContentRole, ...]


@dataclass(frozen=True, slots=True)
class _StructuredParagraph:
    paragraph_ref: str
    labels: tuple[_StructuredLabel, ...]
    tagging_status: str = "completed"


@dataclass(frozen=True, slots=True)
class _StructuredChunkResult:
    chunk_id: str
    chunk_new_concepts: tuple[str, ...]
    paragraphs: tuple[_StructuredParagraph, ...]

    @classmethod
    def model_json_schema(cls) -> dict[str, object]:
        label_schema = {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "generated_concept",
                "action",
                "resolved_concept",
                "roles",
            ],
            "properties": {
                "generated_concept": {"type": "string", "minLength": 1},
                "action": {
                    "type": "string",
                    "enum": [
                        "reuse_existing",
                        "reuse_chunk_new",
                        "create_new",
                    ],
                },
                "resolved_concept": {"type": "string", "minLength": 1},
                "roles": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "enum": [role.value for role in ContentRole],
                    },
                },
            },
        }
        paragraph_schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["paragraph_ref", "labels", "tagging_status"],
            "properties": {
                "paragraph_ref": {"type": "string", "minLength": 1},
                "labels": {
                    "type": "array",
                    "items": label_schema,
                },
                "tagging_status": {"type": "string", "const": "completed"},
            },
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["chunk_id", "chunk_new_concepts", "paragraphs"],
            "properties": {
                "chunk_id": {"type": "string", "minLength": 1},
                "chunk_new_concepts": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1},
                },
                "paragraphs": {
                    "type": "array",
                    "minItems": 1,
                    "items": paragraph_schema,
                },
            },
        }

    @classmethod
    def model_validate(cls, value: object) -> "_StructuredChunkResult":
        payload = _mapping(value, "chunk tagging output")
        _exact_keys(payload, {"chunk_id", "chunk_new_concepts", "paragraphs"})
        concepts = _string_list(payload.get("chunk_new_concepts"), "chunk_new_concepts")
        raw_paragraphs = _list(payload.get("paragraphs"), "paragraphs")
        paragraphs: list[_StructuredParagraph] = []
        for raw_paragraph in raw_paragraphs:
            paragraph = _mapping(raw_paragraph, "paragraph")
            _exact_keys(paragraph, {"paragraph_ref", "labels", "tagging_status"})
            raw_labels = _list(paragraph.get("labels"), "labels")
            labels: list[_StructuredLabel] = []
            for raw_label in raw_labels:
                label = _mapping(raw_label, "label")
                _exact_keys(
                    label,
                    {"generated_concept", "action", "resolved_concept", "roles"},
                )
                action = _text(label.get("action"), "action")
                if action not in {"reuse_existing", "reuse_chunk_new", "create_new"}:
                    raise ValueError("action is invalid")
                labels.append(
                    _StructuredLabel(
                        _text(label.get("generated_concept"), "generated_concept"),
                        action,
                        _text(label.get("resolved_concept"), "resolved_concept"),
                        tuple(
                            ContentRole(role)
                            for role in _string_list(label.get("roles"), "roles")
                        ),
                    )
                )
            paragraphs.append(
                _StructuredParagraph(
                    _text(paragraph.get("paragraph_ref"), "paragraph_ref"),
                    tuple(labels),
                    _text(paragraph.get("tagging_status"), "tagging_status"),
                )
            )
        return cls(
            _text(payload.get("chunk_id"), "chunk_id"),
            concepts,
            tuple(paragraphs),
        )


@dataclass(frozen=True, slots=True)
class _ParagraphRefAliases:
    """Request-local aliases that keep durable paragraph IDs away from the LLM."""

    aliases: tuple[str, ...]
    original_refs: tuple[str, ...]

    @classmethod
    def from_request(cls, request: ChunkTaggingRequest) -> "_ParagraphRefAliases":
        original_refs = tuple(
            item.paragraph.paragraph_id for item in request.paragraphs
        )
        aliases = tuple(f"p{index}" for index in range(1, len(original_refs) + 1))
        return cls(aliases, original_refs)

    def alias_for(self, original_ref: str) -> str:
        try:
            index = self.original_refs.index(original_ref)
        except ValueError as error:
            raise ValueError("paragraph ref is not present in the alias map") from error
        return self.aliases[index]

    def restore(
        self,
        paragraphs: tuple[_StructuredParagraph, ...],
    ) -> tuple[_StructuredParagraph, ...]:
        seen: set[str] = set()
        restored: list[_StructuredParagraph] = []
        for paragraph in paragraphs:
            alias = paragraph.paragraph_ref
            if alias in seen:
                raise ValueError(f"duplicate paragraph alias: {alias}")
            seen.add(alias)
            try:
                index = self.aliases.index(alias)
            except ValueError as error:
                raise ValueError(f"unknown paragraph alias: {alias}") from error
            restored.append(
                _StructuredParagraph(
                    self.original_refs[index],
                    paragraph.labels,
                    paragraph.tagging_status,
                )
            )
        if seen != set(self.aliases):
            raise ValueError(
                "returned paragraph aliases must exactly match request aliases"
            )
        return tuple(restored)


class StructuredChunkTagger(ChunkTagger):
    """Map the chunk contract through the provider shared by all topic LLM tasks."""

    def __init__(self, provider: StructuredLlmProvider) -> None:
        if not callable(getattr(provider, "generate_structured", None)):
            raise TypeError("provider must provide generate_structured")
        self._provider = provider

    async def tag(self, request: ChunkTaggingRequest) -> ChunkTaggingResult:
        if not isinstance(request, ChunkTaggingRequest):
            raise TypeError("request must be a ChunkTaggingRequest")
        paragraph_aliases = _ParagraphRefAliases.from_request(request)
        payload = await self._provider.generate_structured(
            task_type="chunk_tagging_and_conflict",
            system_prompt=(
                "Assign canonical concepts and supported content roles to every supplied "
                "paragraph. Return exactly one strict JSON object matching the output contract. "
                "Return every request-local paragraph alias exactly once. Never echo source fields such "
                "as target_text, heading_path, previous_context, next_context, image_context, "
                "or existing_candidates into the output. Do not add any fields. "
                "Within each paragraph, emit at most one label for each generated_concept; "
                "merge multiple roles for the same concept into that label."
            ),
            user_prompt=_chunk_prompt(request, paragraph_aliases),
            response_model=_StructuredChunkResult,
        )
        restored_paragraphs = paragraph_aliases.restore(payload.paragraphs)
        result = ChunkTaggingResult(
            payload.chunk_id,
            tuple(payload.chunk_new_concepts),
            tuple(
                ChunkParagraphTaggingResult(
                    paragraph.paragraph_ref,
                    tuple(
                        ChunkTaggingLabel(
                            label.generated_concept,
                            label.action,
                            label.resolved_concept,
                            tuple(label.roles),
                        )
                        for label in paragraph.labels
                    ),
                    paragraph.tagging_status,
                )
                for paragraph in restored_paragraphs
            ),
        )
        result.validate_against(request)
        return result


def _chunk_prompt(
    request: ChunkTaggingRequest,
    paragraph_aliases: _ParagraphRefAliases | None = None,
) -> str:
    resolved_aliases = paragraph_aliases or _ParagraphRefAliases.from_request(request)
    request_payload = {
        "chunk_id": request.chunk_id,
        "role_enum": [role.value for role in ContentRole],
        "paragraphs": [
            {
                "paragraph_ref": resolved_aliases.alias_for(
                    item.paragraph.paragraph_id
                ),
                "heading_path": list(item.paragraph.heading_path),
                "previous_context": item.previous_context,
                "target_text": item.paragraph.text,
                "next_context": item.next_context,
                "image_context": list(item.image_context),
                "existing_candidates": list(item.existing_candidates),
            }
            for item in request.paragraphs
        ],
    }
    payload = {
        "instructions": {
            "response_format": "json_object",
            "top_level_keys": ["chunk_id", "chunk_new_concepts", "paragraphs"],
            "paragraph_keys": ["paragraph_ref", "labels", "tagging_status"],
            "label_keys": [
                "generated_concept",
                "action",
                "resolved_concept",
                "roles",
            ],
            "copy_example_ids": False,
            "rules": [
                "Return only the output keys listed above and no source/context fields.",
                "paragraph_ref values are request-local aliases such as p1 and p2.",
                "Return every request paragraph_ref exactly once and do not invent, expand, or rewrite aliases.",
                "Use tagging_status completed for every paragraph.",
                "For reuse_existing, resolved_concept must exactly match an existing candidate.",
                "For create_new or reuse_chunk_new, resolved_concept must appear in chunk_new_concepts.",
                "Use create_new for the first introduction of a new chunk concept and reuse_chunk_new for later reuse.",
                "Each label must contain at least one role from role_enum.",
                "Use one label per generated concept within each paragraph; never repeat a generated_concept.",
                "If one concept has multiple roles, merge all roles into that single label.",
                "Before returning, compare generated_concept values within each paragraph and merge duplicates.",
            ],
        },
        "few_shot_examples": _few_shot_examples(),
        "request": request_payload,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)


def _few_shot_examples() -> list[dict[str, object]]:
    return [
        {
            "input": {
                "chunk_id": "example-chunk-reuse",
                "paragraphs": [
                    {
                        "paragraph_ref": "p1",
                        "target_text": "A major triad contains a root, major third, and perfect fifth.",
                        "existing_candidates": ["Major triad"],
                    }
                ],
            },
            "output": {
                "chunk_id": "example-chunk-reuse",
                "chunk_new_concepts": [],
                "paragraphs": [
                    {
                        "paragraph_ref": "p1",
                        "labels": [
                            {
                                "generated_concept": "Major chord",
                                "action": "reuse_existing",
                                "resolved_concept": "Major triad",
                                "roles": ["Definition"],
                            }
                        ],
                        "tagging_status": "completed",
                    }
                ],
            },
        },
        {
            "input": {
                "chunk_id": "example-chunk-new",
                "paragraphs": [
                    {
                        "paragraph_ref": "p1",
                        "target_text": "The circle of fifths arranges keys by perfect fifths.",
                        "existing_candidates": [],
                    },
                    {
                        "paragraph_ref": "p2",
                        "target_text": "Use the circle clockwise to find the next sharp key.",
                        "existing_candidates": [],
                    },
                ],
            },
            "output": {
                "chunk_id": "example-chunk-new",
                "chunk_new_concepts": ["Circle of fifths"],
                "paragraphs": [
                    {
                        "paragraph_ref": "p1",
                        "labels": [
                            {
                                "generated_concept": "Circle of fifths",
                                "action": "create_new",
                                "resolved_concept": "Circle of fifths",
                                "roles": ["Definition"],
                            }
                        ],
                        "tagging_status": "completed",
                    },
                    {
                        "paragraph_ref": "p2",
                        "labels": [
                            {
                                "generated_concept": "Circle of fifths usage",
                                "action": "reuse_chunk_new",
                                "resolved_concept": "Circle of fifths",
                                "roles": ["Procedure"],
                            }
                        ],
                        "tagging_status": "completed",
                    },
                ],
            },
        },
        {
            "input": {
                "chunk_id": "example-chunk-merge-roles",
                "paragraphs": [
                    {
                        "paragraph_ref": "p1",
                        "target_text": "Harmony describes how chords and progressions relate in a musical passage.",
                        "existing_candidates": [],
                    }
                ],
            },
            "output": {
                "chunk_id": "example-chunk-merge-roles",
                "chunk_new_concepts": ["Harmony"],
                "paragraphs": [
                    {
                        "paragraph_ref": "p1",
                        "labels": [
                            {
                                "generated_concept": "Harmony",
                                "action": "create_new",
                                "resolved_concept": "Harmony",
                                "roles": ["Definition", "Explanation"],
                            }
                        ],
                        "tagging_status": "completed",
                    }
                ],
            },
        },
    ]


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")
    return value.strip()


def _string_list(value: object, name: str) -> tuple[str, ...]:
    return tuple(_text(item, name) for item in _list(value, name))


def _exact_keys(value: Mapping[str, object], allowed: set[str]) -> None:
    if set(value) != allowed:
        raise ValueError("structured output fields do not match the contract")
