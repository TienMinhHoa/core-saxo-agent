"""LangChain-backed synthesis of an immutable evidence ledger."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Self

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import Citation, EvidenceLedger, SynthesisResult
from .prompts import SYNTHESIS_PROMPT


class SynthesisCitation(BaseModel):
    """Structured citation returned by the LangChain model."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    evidence_id: str = Field(min_length=1)
    label: str = Field(min_length=1)


class SynthesisOutput(BaseModel):
    """Validated model output before it is mapped to the domain DTO."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    answer: str = Field(min_length=1)
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
        if not ledger.evidence:
            raise ValueError("ledger must contain evidence before synthesis")

        payload = {
            "question": ledger.question,
            "evidence_ledger": _render_ledger(ledger),
        }
        raw_output = await self._chain.ainvoke(payload, config=config or {})
        output = _coerce_output(raw_output)
        result = SynthesisResult(
            answer=output.answer,
            used_evidence_ids=tuple(output.used_evidence_ids),
            citations=tuple(
                Citation(citation.evidence_id, citation.label)
                for citation in output.citations
            ),
            image_evidence_ids=tuple(output.image_evidence_ids),
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
    for item in ledger.evidence:
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
                f"  source_type: {item.source_type.value}",
                f"  source: {source}",
                f"  scope: {', '.join(scope) or 'unspecified'}",
                f"  image_refs: {image_refs}",
                f"  text: {item.text}",
            )
        )
    return "\n".join(lines)


__all__ = [
    "EvidenceSynthesisService",
    "SynthesisCitation",
    "SynthesisOutput",
]
