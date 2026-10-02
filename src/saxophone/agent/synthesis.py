"""LangChain-backed synthesis of an immutable evidence ledger."""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Self

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import Citation, EvidenceLedger, SynthesisResult
from .prompts import SYNTHESIS_PROMPT


class SynthesisCitation(BaseModel):
    """Structured citation returned by the LangChain model."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    evidence_id: str = Field(min_length=1)
    label: str = Field(min_length=1, description="Exact bracketed citation_label from the ledger, such as [1]. Keep the square brackets.")


class SynthesisOutput(BaseModel):
    """Validated model output before it is mapped to the domain DTO."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    answer: str = Field(min_length=1)
    evidence_sufficient: bool
    used_evidence_ids: list[str] = Field(default_factory=list)
    citations: list[SynthesisCitation] = Field(default_factory=list)
    image_evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> Self:
        if len(self.used_evidence_ids) != len(set(self.used_evidence_ids)):
            raise ValueError("used_evidence_ids must be unique")
        if len(self.image_evidence_ids) != len(set(self.image_evidence_ids)):
            raise ValueError("image_evidence_ids must be unique")
        citation_ids = [citation.evidence_id for citation in self.citations]
        if len(citation_ids) != len(set(citation_ids)):
            raise ValueError("citation evidence ids must be unique")
        labels = [citation.label for citation in self.citations]
        if len(labels) != len(set(labels)):
            raise ValueError("citation labels must be unique")
        return self


_INLINE_CITATION = re.compile(r"\[[0-9]+\]")
_INTERNAL_KNOWLEDGE_NOTICE = (
    "Tạm thời chưa tìm thấy đủ thông tin trong các nguồn đã tra cứu. "
    "Tôi sẽ dùng kiến thức nội tại để trả lời."
)


def _normalize_inline_citations(output: SynthesisOutput) -> tuple[str, tuple[Citation, ...]]:
    """Validate source references, then renumber text and metadata together."""

    labels = {citation.label for citation in output.citations}
    if any(re.fullmatch(r"\[[1-9][0-9]*\]", label) is None for label in labels):
        raise ValueError("citation labels must be numeric, such as [1]")
    inline_labels = set(_INLINE_CITATION.findall(output.answer))
    if inline_labels != labels:
        raise ValueError("inline citations must match the listed source labels")
    cited_ids = {citation.evidence_id for citation in output.citations}
    if set(output.used_evidence_ids) != cited_ids:
        raise ValueError("used evidence must have matching inline citations")
    replacements = {citation.label: f"[{index}]" for index, citation in enumerate(output.citations, start=1)}
    # A single substitution avoids cascading replacements when labels are swapped.
    answer = _INLINE_CITATION.sub(lambda match: replacements[match.group()], output.answer)
    citations = tuple(Citation(citation.evidence_id, replacements[citation.label]) for citation in output.citations)
    return answer, citations


class EvidenceSynthesisService:
    """Run one structured LangChain synthesis chain over a validated ledger."""

    def __init__(self, model: object) -> None:
        with_structured_output = getattr(model, "with_structured_output", None)
        if not callable(with_structured_output):
            raise TypeError("model must provide with_structured_output")
        structured_runnable = with_structured_output(SynthesisOutput)
        if not callable(getattr(structured_runnable, "ainvoke", None)):
            raise TypeError("structured model must provide an async runnable")
        self._chain = SYNTHESIS_PROMPT | structured_runnable

    @property
    def chain(self) -> object:
        """Expose the composed runnable for composition and callback wiring."""

        return self._chain

    async def synthesize(
        self,
        ledger: EvidenceLedger,
        *,
        config: RunnableConfig | None = None,
    ) -> SynthesisResult:
        """Return validated synthesis output for one immutable evidence ledger."""

        if not isinstance(ledger, EvidenceLedger):
            raise TypeError("ledger must be an EvidenceLedger")
        payload = {
            "question": ledger.question,
            "chat_history": json.dumps(
                [{"role": item.role, "content": item.content} for item in ledger.history],
                ensure_ascii=False,
            ),
            "evidence_ledger": _render_ledger(ledger),
            "budget_status": json.dumps({
                "budget_exhausted": ledger.budget_exhausted,
                "budget_reason": ledger.budget_reason,
            }),
        }
        raw_output = await self._chain.ainvoke(payload, config=config or {})
        output = _coerce_output(raw_output)
        # Validate evidence identities before considering display labels.
        SynthesisResult(
            output.answer, tuple(output.used_evidence_ids),
            tuple(Citation(item.evidence_id, item.label) for item in output.citations),
            tuple(output.image_evidence_ids),
        ).validate_against(ledger)
        answer, citations = _normalize_inline_citations(output)
        if output.evidence_sufficient and not output.used_evidence_ids:
            raise ValueError("sufficient evidence requires at least one cited source")
        if not output.evidence_sufficient:
            answer = f"{_INTERNAL_KNOWLEDGE_NOTICE}\n\n{answer}"
        used_ids = tuple(output.used_evidence_ids)
        image_ids = tuple(output.image_evidence_ids)
        if output.evidence_sufficient and _requests_source_image(ledger.question):
            available_image_ids = tuple(item.evidence_id for item in ledger.evidence if item.image_refs)
            image_ids = tuple(dict.fromkeys((*image_ids, *available_image_ids)))
            used_ids = tuple(dict.fromkeys((*used_ids, *available_image_ids)))
        result = SynthesisResult(
            answer=answer,
            used_evidence_ids=used_ids,
            citations=citations,
            image_evidence_ids=image_ids,
            evidence_sufficient=output.evidence_sufficient,
        )
        result.validate_against(ledger)
        return result


def _coerce_output(value: object) -> SynthesisOutput:
    if isinstance(value, SynthesisOutput):
        return value
    if isinstance(value, BaseModel):
        value = value.model_dump()
    if isinstance(value, Mapping):
        return SynthesisOutput.model_validate(value)
    raise TypeError("structured synthesis output must be a mapping")


def _render_ledger(ledger: EvidenceLedger) -> str:
    """Render only source facts needed by synthesis, with stable evidence ids."""

    lines = ["Use the following evidence records as the complete source:"]
    for index, item in enumerate(ledger.evidence, start=1):
        source = item.source_ref or item.url or "unknown source"
        scope: list[str] = []
        if item.chunk:
            scope.append(f"chunk={item.chunk}")
        if item.paragraph:
            scope.append(f"paragraph={item.paragraph}")
        if item.page is not None:
            scope.append(f"page={item.page}")
        if item.url:
            scope.append(f"url={item.url}")
        image_refs = ", ".join(item.image_refs) or "none"
        lines.extend(
            (
                f"- evidence_id: {item.evidence_id}",
                f"  citation_label: [{index}]",
                f"  source_type: {item.source_type.value}",
                f"  source: {source}",
                f"  scope: {', '.join(scope) or 'unspecified'}",
                f"  image_refs: {image_refs}",
                f"  text: {item.text}",
            )
        )
    return "\n".join(lines)


def _requests_source_image(question: str) -> bool:
    lowered = question.casefold()
    return bool(
        re.search(r"\b(?:figure|image|diagram|illustration)\b", lowered)
        and re.search(r"\b(?:include|show|display|attach|provide)\b", lowered)
    )


__all__ = [
    "EvidenceSynthesisService",
    "SynthesisCitation",
    "SynthesisOutput",
]
