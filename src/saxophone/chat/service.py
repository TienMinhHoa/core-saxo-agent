"""Chat application use case, independent from model and retrieval SDKs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from saxophone.retrieval import EvidenceBundle, RetrieveEvidence
from saxophone.retrieval.question_retrieval import (
    QuestionRequest,
    RetrievalBundleStatus,
)
from saxophone.tagging.structured_provider import StructuredLlmProvider

from .models import ChatResult, ChatStatus, evidence_reference
from .ports import AnswerGenerator, ImageArtifactGate


class AnswerQuestion:
    """Retrieve validated evidence, then delegate grounded synthesis."""

    def __init__(
        self,
        retrieve_evidence: RetrieveEvidence,
        answer_generator: AnswerGenerator,
        image_artifact_gate: ImageArtifactGate | None = None,
    ) -> None:
        self._retrieve_evidence = retrieve_evidence
        self._answer_generator = answer_generator
        self._image_artifact_gate = image_artifact_gate

    async def execute(
        self,
        question: str,
        *,
        filters: Mapping[str, object] | None = None,
        limit: int = 10,
    ) -> ChatResult:
        normalized_question = question.strip() if isinstance(question, str) else question
        evidence = await self._retrieve_evidence.execute(
            normalized_question, filters=filters, limit=limit
        )
        if not evidence.hits:
            return ChatResult(
                ChatStatus.INSUFFICIENT_EVIDENCE,
                None,
                (),
                None,
                None,
                {},
                0.0,
                evidence.insufficiency_reason,
            )

        if evidence.image_refs:
            if self._image_artifact_gate is None:
                raise ValueError("image artifact gate is required for image evidence")
            gated_images = await self._image_artifact_gate.validate(evidence.image_refs)
            evidence = EvidenceBundle(
                evidence.query, evidence.retrieval_version, evidence.hits,
                evidence.selected_refs, evidence.source_texts, gated_images,
            )

        generated = await self._answer_generator.generate(normalized_question, evidence)
        citations = tuple(dict.fromkeys(hit.source_ref for hit in evidence.hits))
        return ChatResult(
            ChatStatus.ANSWERED,
            generated.answer,
            citations,
            evidence_reference(evidence.retrieval_version, evidence.selected_refs),
            generated.model_version,
            generated.token_usage,
            generated.cost,
        )


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
    def model_validate(cls, value: object) -> "_StructuredAnswer":
        if not isinstance(value, Mapping):
            raise ValueError("answer output must be a mapping")
        if set(value) != {"answer", "used_paragraph_refs"}:
            raise ValueError("answer output fields do not match the contract")
        answer = _non_blank_text(value.get("answer"), "answer")
        raw_refs = value.get("used_paragraph_refs")
        if not isinstance(raw_refs, list):
            raise ValueError("used_paragraph_refs must be a list")
        refs = tuple(
            _non_blank_text(item, "used_paragraph_refs") for item in raw_refs
        )
        if len(refs) != len(set(refs)):
            raise ValueError("used_paragraph_refs must be unique")
        return cls(answer, refs)


class GroundedAnswerService:
    """Retrieve concept-role paragraphs and synthesize a reference-validated answer."""

    def __init__(
        self,
        answer_question: AnswerQuestion | None = None,
        *,
        retrieval: object | None = None,
        provider: StructuredLlmProvider | None = None,
        model_version: str | None = None,
    ) -> None:
        legacy = answer_question is not None
        structured = retrieval is not None or provider is not None or model_version is not None
        if legacy and structured:
            raise ValueError("legacy and structured answer collaborators are mutually exclusive")
        if legacy:
            if not callable(getattr(answer_question, "execute", None)):
                raise ValueError("answer_question must provide execute")
            self._answer_question = answer_question
            self._retrieval = None
            self._provider = None
            self._model_version = None
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

    async def answer(self, request: QuestionRequest) -> ChatResult | GroundedAnswerResponse:
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
                "Answer only from the supplied paragraph context and cite only paragraph "
                "references present in that context."
            ),
            user_prompt=bundle.answer_context_markdown.strip(),
            response_model=_StructuredAnswer,
        )
        paragraphs = {
            paragraph.paragraph_ref: paragraph
            for paragraph in bundle.answer_context.paragraphs
        }
        refs = tuple(payload.used_paragraph_refs)
        if len(refs) != len(set(refs)):
            raise ValueError("used paragraph refs must be unique")
        if any(ref not in paragraphs for ref in refs):
            raise ValueError("used paragraph refs must belong to retrieved paragraph context")
        sources = tuple(_answer_source(paragraphs[ref]) for ref in refs)
        return GroundedAnswerResponse(
            GroundedAnswerStatus.ANSWERED,
            payload.answer,
            sources,
            self._model_version,
        )


def _answer_source(paragraph: object) -> AnswerSource:
    pages = tuple(getattr(paragraph, "pages", ()))
    numeric_pages = tuple(int(page) for page in pages if str(page).isdigit())
    return AnswerSource(
        paragraph_ref=getattr(paragraph, "paragraph_ref"),
        chunk_id=getattr(paragraph, "chunk_id"),
        source=getattr(paragraph, "source"),
        page_start=numeric_pages[0] if numeric_pages else None,
        page_end=numeric_pages[-1] if numeric_pages else None,
        image_refs=tuple(getattr(paragraph, "image_refs", ())),
    )


def _non_blank_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value.strip()
