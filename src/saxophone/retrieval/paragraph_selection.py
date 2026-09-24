"""Paragraph-level candidate selection for grounded question answering."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from saxophone.tagging.structured_provider import StructuredLlmProvider

from .renderers import SourceParagraph


@dataclass(frozen=True, slots=True)
class ParagraphChoice:
    """One numbered paragraph candidate exposed to the selector model."""

    key: str
    paragraph_ref: str
    paragraph: SourceParagraph

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.isdigit() or int(self.key) < 1:
            raise ValueError("paragraph choice key must be a positive integer string")
        if not isinstance(self.paragraph_ref, str) or not self.paragraph_ref.strip():
            raise ValueError("paragraph_ref must be non-blank")
        if not isinstance(self.paragraph, SourceParagraph):
            raise ValueError("paragraph must be a SourceParagraph")
        if self.paragraph.paragraph_ref != self.paragraph_ref:
            raise ValueError("paragraph_ref must match paragraph.paragraph_ref")


@dataclass(frozen=True, slots=True)
class ParagraphSelectionRequest:
    question: str
    choices: tuple[ParagraphChoice, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.question, str) or not self.question.strip():
            raise ValueError("question must be non-blank")
        if not self.choices:
            raise ValueError("choices must not be empty")
        keys = tuple(choice.key for choice in self.choices)
        refs = tuple(choice.paragraph_ref for choice in self.choices)
        if len(keys) != len(set(keys)):
            raise ValueError("choice keys must be unique")
        if len(refs) != len(set(refs)):
            raise ValueError("choice paragraph refs must be unique")
        object.__setattr__(self, "question", self.question.strip())
        object.__setattr__(self, "choices", tuple(self.choices))


@dataclass(frozen=True, slots=True)
class ParagraphSelection:
    reason: str
    key: str

    def __post_init__(self) -> None:
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("selection reason must be non-blank")
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("selection key must be non-blank")
        object.__setattr__(self, "reason", self.reason.strip())
        object.__setattr__(self, "key", self.key.strip())


@dataclass(frozen=True, slots=True)
class ParagraphSelectionResult:
    selections: tuple[ParagraphSelection, ...]

    @classmethod
    def model_json_schema(cls) -> dict[str, object]:
        item = {
            "type": "object",
            "additionalProperties": False,
            "required": ["reason", "key"],
            "properties": {
                "reason": {"type": "string", "minLength": 1},
                "key": {"type": "string", "minLength": 1},
            },
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["selections"],
            "properties": {
                "selections": {"type": "array", "items": item},
            },
        }

    @classmethod
    def model_validate(cls, value: object) -> "ParagraphSelectionResult":
        if not isinstance(value, dict) or set(value) != {"selections"}:
            raise ValueError("paragraph selection output fields do not match the contract")
        raw = value["selections"]
        if not isinstance(raw, list):
            raise ValueError("selections must be a list")
        selections: list[ParagraphSelection] = []
        for item in raw:
            if not isinstance(item, dict) or set(item) != {"reason", "key"}:
                raise ValueError("selection fields must be exactly reason and key")
            selections.append(ParagraphSelection(item["reason"], item["key"]))
        result = cls(tuple(selections))
        keys = tuple(selection.key for selection in result.selections)
        if len(keys) != len(set(keys)):
            raise ValueError("selected paragraph keys must be unique")
        return result

    def validate_against(self, request: ParagraphSelectionRequest) -> None:
        allowed = {choice.key for choice in request.choices}
        if any(selection.key not in allowed for selection in self.selections):
            raise ValueError("selected paragraph key must be present in choices")


def build_paragraph_choices(
    paragraphs: Sequence[SourceParagraph],
) -> tuple[ParagraphChoice, ...]:
    """Deduplicate exact paragraph content, merge metadata, and assign numeric keys."""

    merged: dict[str, SourceParagraph] = {}
    content_refs: dict[str, str] = {}
    for paragraph in paragraphs:
        if not isinstance(paragraph, SourceParagraph):
            raise ValueError("paragraphs must contain SourceParagraph values")
        existing_ref = paragraph.paragraph_ref
        content_key = _normalized_text(paragraph.text)
        if existing_ref not in merged and content_key:
            existing_ref = content_refs.get(content_key, existing_ref)
        current = merged.get(existing_ref)
        merged[existing_ref] = paragraph if current is None else _merge(current, paragraph)
        if content_key:
            content_refs.setdefault(content_key, existing_ref)
    return tuple(
        ParagraphChoice(str(index), paragraph_ref, paragraph)
        for index, (paragraph_ref, paragraph) in enumerate(merged.items(), start=1)
    )


def render_paragraph_choices(
    question: str,
    choices: Sequence[ParagraphChoice],
) -> str:
    request = ParagraphSelectionRequest(question, tuple(choices))
    lines = [
        "# Paragraph Selection",
        "",
        "## User question",
        "",
        request.question,
        "",
        "## Candidate paragraphs",
        "",
    ]
    for choice in request.choices:
        paragraph = choice.paragraph
        lines.extend(
            (
                f"{choice.key}: {paragraph.parent_header}",
                f"Paragraph ref: {paragraph.paragraph_ref}",
                f"Source: {paragraph.source}",
                f"Nested headings: {'; '.join(paragraph.nested_headings) if paragraph.nested_headings else 'none'}",
                f"Pages: {'-'.join(paragraph.pages) if paragraph.pages else 'none'}",
                f"Concepts and roles: {'; '.join(paragraph.concepts_and_roles) if paragraph.concepts_and_roles else 'none'}",
                f"Images: {', '.join(paragraph.image_refs) if paragraph.image_refs else 'none'}",
                "Text:",
                paragraph.text,
                "",
            )
        )
    return "\n".join(lines).strip()


class StructuredParagraphSelector:
    """Use the structured provider to select numbered paragraph choices."""

    def __init__(self, provider: StructuredLlmProvider) -> None:
        if not callable(getattr(provider, "generate_structured", None)):
            raise TypeError("provider must provide generate_structured")
        self._provider = provider

    async def select(self, request: ParagraphSelectionRequest) -> ParagraphSelectionResult:
        if not isinstance(request, ParagraphSelectionRequest):
            raise ValueError("request must be a ParagraphSelectionRequest")
        payload = await self._provider.generate_structured(
            task_type="paragraph_selection",
            system_prompt=(
                "Select only the numbered paragraphs relevant to the user question. "
                "Return exactly one JSON object with only the key selections. "
                "Each selection must contain reason first and key second. "
                "Do not invent keys, do not duplicate keys, and do not add any other fields."
            ),
            user_prompt=_selection_prompt(request),
            response_model=ParagraphSelectionResult,
        )
        if not isinstance(payload, ParagraphSelectionResult):
            raise ValueError("paragraph selector must return ParagraphSelectionResult")
        payload.validate_against(request)
        return payload


def _selection_prompt(request: ParagraphSelectionRequest) -> str:
    choices = render_paragraph_choices(request.question, request.choices)
    return "\n\n".join(
        (
            choices,
            "## Output contract",
            "Return exactly one JSON object.",
            "Use only these keys in each selection, in this order: reason, key.",
            "Select only enough paragraphs to answer the question.",
            "If two paragraphs express the same information, select only one.",
            "## Few-shot examples",
            '{"selections":[{"reason":"The paragraph directly defines the requested concept.","key":"1"}]}',
            '{"selections":[{"reason":"This paragraph explains the relationship asked about.","key":"2"}]}',
        )
    )


def _merge(left: SourceParagraph, right: SourceParagraph) -> SourceParagraph:
    return SourceParagraph(
        paragraph_ref=left.paragraph_ref,
        source=right.source or left.source,
        parent_header=right.parent_header or left.parent_header,
        nested_headings=_merge_values(left.nested_headings, right.nested_headings),
        text=right.text or left.text,
        concepts_and_roles=_merge_values(left.concepts_and_roles, right.concepts_and_roles),
        pages=_merge_values(left.pages, right.pages),
        image_refs=_merge_values(left.image_refs, right.image_refs),
        chunk_id=right.chunk_id or left.chunk_id,
    )


def _merge_values(left: Sequence[str], right: Sequence[str]) -> tuple[str, ...]:
    values: list[str] = []
    for value in (*left, *right):
        if value and value not in values:
            values.append(value)
    return tuple(values)


def _normalized_text(value: str) -> str:
    return " ".join(value.split()).casefold()
