"""Compatibility adapter for the pre-agent grounded chat endpoint.

The Main Agent owns the new LangGraph synthesis path.  This module keeps the
legacy retrieval and structured-provider contract isolated so the old JSON
endpoint can remain available during migration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

from saxophone.documents.policies import is_safe_relative_image_reference
from saxophone.retrieval.question_retrieval import (
    QuestionRequest,
    RetrievalBundleStatus,
)
from saxophone.tagging.structured_provider import StructuredLlmProvider

from .models import ChatResult
from .ports import ImageArtifactGate

if TYPE_CHECKING:
    from .service import AnswerQuestion


class GroundedAnswerStatus(StrEnum):
    ANSWERED = "answered"
    NO_RETRIEVAL_CONTEXT = "no_retrieval_context"
    NO_RELEVANT_CONCEPT_ROLE = "no_relevant_concept_role"


@dataclass(frozen=True, slots=True)
class AnswerSource:
    paragraph_ref: str
    chunk_id: str
    source: str
    page_start: int | None = None
    page_end: int | None = None
    image_refs: tuple[str, ...] = ()
    image_captions: Mapping[str, str] = field(default_factory=dict)
    image_errors: tuple[str, ...] = ()
    citation: str | None = None
    score: float | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.image_refs, tuple):
            raise ValueError("image_refs must be a tuple")
        if len(set(self.image_refs)) != len(self.image_refs):
            raise ValueError("image_refs must be unique")
        if not isinstance(self.image_errors, tuple):
            raise ValueError("image_errors must be a tuple")
        if any(
            not isinstance(error, str) or not error.strip()
            for error in self.image_errors
        ):
            raise ValueError("image_errors must contain non-blank strings")
        if not isinstance(self.image_captions, Mapping):
            raise ValueError("image_captions must be a mapping")
        if any(ref not in self.image_refs for ref in self.image_captions):
            raise ValueError("image_captions must reference image_refs")
        if any(
            not isinstance(caption, str) or not caption.strip()
            for caption in self.image_captions.values()
        ):
            raise ValueError("image_captions must contain non-blank strings")
        object.__setattr__(self, "image_refs", tuple(self.image_refs))
        object.__setattr__(self, "image_errors", tuple(self.image_errors))
        object.__setattr__(
            self,
            "image_captions",
            MappingProxyType(dict(self.image_captions)),
        )


@dataclass(frozen=True, slots=True)
class GroundedAnswerResponse:
    status: GroundedAnswerStatus
    answer: str | None
    sources: tuple[AnswerSource, ...]
    model_version: str | None = None


@dataclass(frozen=True, slots=True)
class _StructuredAnswer:
    answer: str
    used_paragraph_refs: tuple[str, ...]

    @classmethod
    def model_json_schema(cls) -> dict[str, object]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer", "used_paragraph_refs"],
            "properties": {
                "answer": {"type": "string", "minLength": 1},
                "used_paragraph_refs": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
            },
        }

    @classmethod
    def model_validate(cls, value: object) -> _StructuredAnswer:
        if not isinstance(value, Mapping):
            raise ValueError("answer output must be a mapping")
        if set(value) != {"answer", "used_paragraph_refs"}:
            raise ValueError("answer output fields do not match the contract")
        answer = _non_blank_text(value.get("answer"), "answer")
        raw_refs = value.get("used_paragraph_refs")
        if not isinstance(raw_refs, list):
            raise ValueError("used_paragraph_refs must be a list")
        refs = tuple(_non_blank_text(item, "used_paragraph_refs") for item in raw_refs)
        if len(refs) != len(set(refs)):
            raise ValueError("used_paragraph_refs must be unique")
        return cls(answer, refs)


class GroundedAnswerService:
    """Compatibility adapter for retrieval-backed grounded answers."""

    def __init__(
        self,
        answer_question: AnswerQuestion | None = None,
        *,
        retrieval: object | None = None,
        provider: StructuredLlmProvider | None = None,
        model_version: str | None = None,
        image_artifact_gate: ImageArtifactGate | None = None,
    ) -> None:
        legacy = answer_question is not None
        structured = (
            retrieval is not None or provider is not None or model_version is not None
        )
        if legacy and structured:
            raise ValueError(
                "legacy and structured answer collaborators are mutually exclusive"
            )
        if legacy:
            if not callable(getattr(answer_question, "execute", None)):
                raise ValueError("answer_question must provide execute")
            self._answer_question = answer_question
            self._retrieval = None
            self._provider = None
            self._model_version = None
            self._image_artifact_gate = None
            return
        if not callable(getattr(retrieval, "retrieve", None)):
            raise ValueError("retrieval must provide retrieve")
        if not callable(getattr(provider, "generate_structured", None)):
            raise ValueError("provider must provide generate_structured")
        if not isinstance(model_version, str) or not model_version.strip():
            raise ValueError("model_version must not be blank")
        self._answer_question = None
        self._retrieval = retrieval
        self._provider = provider
        self._model_version = model_version.strip()
        if image_artifact_gate is not None and not callable(
            getattr(image_artifact_gate, "validate", None)
        ):
            raise ValueError("image_artifact_gate must provide validate")
        self._image_artifact_gate = image_artifact_gate

    async def answer(
        self, request: QuestionRequest
    ) -> ChatResult | GroundedAnswerResponse:
        if not isinstance(request, QuestionRequest):
            raise ValueError("request must be a QuestionRequest")
        if self._answer_question is not None:
            return await self._answer_question.execute(
                request.question,
                filters=request.filters,
                limit=request.chunk_limit,
            )
        assert self._retrieval is not None
        assert self._provider is not None
        assert self._model_version is not None
        bundle = await self._retrieval.retrieve(request)
        if bundle.status is RetrievalBundleStatus.NO_RETRIEVAL_CONTEXT:
            return GroundedAnswerResponse(
                GroundedAnswerStatus.NO_RETRIEVAL_CONTEXT,
                None,
                (),
            )
        if bundle.status is RetrievalBundleStatus.NO_RELEVANT_CONCEPT_ROLE:
            return GroundedAnswerResponse(
                GroundedAnswerStatus.NO_RELEVANT_CONCEPT_ROLE,
                None,
                (),
            )
        if bundle.answer_context is None or bundle.answer_context_markdown is None:
            raise ValueError("ready retrieval bundle must contain answer context")
        payload = await self._provider.generate_structured(
            task_type="answer_generation",
            system_prompt=(
                "Answer only from the supplied paragraph context. Cite sources in the answer "
                "using short citation keys such as [1] and [2], never raw paragraph references. "
                "Return used_paragraph_refs as the corresponding numeric citation keys when "
                "possible; do not include any extra fields."
            ),
            user_prompt=bundle.answer_context_markdown.strip(),
            response_model=_StructuredAnswer,
        )
        paragraphs = {
            paragraph.paragraph_ref: paragraph
            for paragraph in bundle.answer_context.paragraphs
        }
        citation_refs = _ordered_context_refs(bundle.answer_context, paragraphs)
        key_to_ref = {
            str(index): ref for index, ref in enumerate(citation_refs, start=1)
        }
        refs = tuple(
            value if value in paragraphs else key_to_ref.get(value, value)
            for value in payload.used_paragraph_refs
        )
        if len(refs) != len(set(refs)):
            raise ValueError("used paragraph refs must be unique")
        if any(ref not in paragraphs for ref in refs):
            raise ValueError(
                "used paragraph refs must belong to retrieved paragraph context"
            )
        sources = tuple(
            _answer_source(paragraphs[ref]) for ref in citation_refs if ref in refs
        )
        if self._image_artifact_gate is not None:
            sources = await _validate_source_images(sources, self._image_artifact_gate)
        return GroundedAnswerResponse(
            GroundedAnswerStatus.ANSWERED,
            _normalize_answer_citations(payload.answer, citation_refs),
            sources,
            self._model_version,
        )


def _answer_source(paragraph: object) -> AnswerSource:
    pages = tuple(getattr(paragraph, "pages", ()))
    numeric_pages = tuple(int(page) for page in pages if str(page).isdigit())
    return AnswerSource(
        paragraph_ref=paragraph.paragraph_ref,
        chunk_id=paragraph.chunk_id,
        source=paragraph.source,
        page_start=numeric_pages[0] if numeric_pages else None,
        page_end=numeric_pages[-1] if numeric_pages else None,
        image_refs=tuple(getattr(paragraph, "image_refs", ())),
        image_captions=getattr(paragraph, "image_captions", {}),
    )


async def _validate_source_images(
    sources: tuple[AnswerSource, ...],
    gate: ImageArtifactGate,
) -> tuple[AnswerSource, ...]:
    validated_sources: list[AnswerSource] = []
    for source in sources:
        valid_refs: list[str] = []
        errors = list(source.image_errors)
        for image_ref in source.image_refs:
            if not is_safe_relative_image_reference(image_ref):
                if "image unavailable" not in errors:
                    errors.append("image unavailable")
                continue
            try:
                validated = await gate.validate((image_ref,))
                if image_ref not in validated:
                    raise ValueError("image reference was not validated")
            except Exception:
                if "image unavailable" not in errors:
                    errors.append("image unavailable")
                continue
            valid_refs.append(image_ref)
        validated_sources.append(
            replace(
                source,
                image_refs=tuple(valid_refs),
                image_errors=tuple(errors),
            )
        )
    return tuple(validated_sources)


def _normalize_answer_citations(
    answer: str,
    citation_refs: tuple[str, ...],
) -> str:
    """Replace leaked internal refs with the short labels shown to the model."""

    labels = {ref: f"[{index}]" for index, ref in enumerate(citation_refs, start=1)}
    normalized = answer
    for ref in sorted(labels, key=len, reverse=True):
        normalized = normalized.replace(ref, labels[ref])
    return normalized


def _ordered_context_refs(
    context: object,
    paragraphs: Mapping[str, object],
) -> tuple[str, ...]:
    selected_refs = tuple(getattr(context, "selected_paragraph_refs", ()))
    if not selected_refs:
        selected_refs = tuple(
            ref
            for selection in getattr(context, "selected_roles", ())
            for ref in selection.paragraph_refs
        )
    return tuple(dict.fromkeys(ref for ref in selected_refs if ref in paragraphs))


def _non_blank_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value.strip()


__all__ = [
    "AnswerSource",
    "GroundedAnswerResponse",
    "GroundedAnswerService",
    "GroundedAnswerStatus",
]
