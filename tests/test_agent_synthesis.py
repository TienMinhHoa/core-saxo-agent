from __future__ import annotations

import pytest
from langchain_core.runnables import RunnableLambda

from saxophone.agent.contracts import (
    Citation,
    EvidenceLedger,
    SelectionStrategy,
)
from saxophone.agent.evidence import EvidenceLedgerBuilder
from saxophone.agent.synthesis import (
    EvidenceSynthesisService,
    SynthesisOutput,
)


class _StructuredModel:
    def __init__(self, response: object) -> None:
        self.response = response
        self.schema: object | None = None
        self.inputs: list[object] = []

    def with_structured_output(self, schema: object) -> RunnableLambda:
        self.schema = schema

        def invoke(prompt_value: object) -> object:
            self.inputs.append(prompt_value)
            return self.response

        return RunnableLambda(invoke)


def _ledger() -> EvidenceLedger:
    builder = EvidenceLedgerBuilder(
        "run-synthesis",
        "What is a major triad?",
        SelectionStrategy.PARAGRAPH_DIRECT,
    )
    builder.add_document(
        source_ref="music-theory.md",
        chunk_id="chunk-1",
        paragraph_ref="paragraph-1",
        text="A major triad has a root, third, and fifth.",
        page=12,
        image_refs=("images/triad.png",),
    )
    builder.add_search_trace("document_search", hit_count=1)
    return builder.build()


@pytest.mark.anyio
async def test_synthesis_service_uses_langchain_structured_runnable_and_maps_to_domain() -> None:
    ledger = _ledger()
    evidence_id = ledger.evidence[0].evidence_id
    model = _StructuredModel(
        {
            "answer": "A major triad has a root, third, and fifth.",
            "used_evidence_ids": [evidence_id],
            "citations": [{"evidence_id": evidence_id, "label": "[1]"}],
            "image_evidence_ids": [evidence_id],
        }
    )

    result = await EvidenceSynthesisService(model).synthesize(ledger)

    assert isinstance(model.schema, type)
    assert model.schema is SynthesisOutput
    assert result.answer.startswith("A major triad")
    assert result.used_evidence_ids == (evidence_id,)
    assert result.citations == (Citation(evidence_id, "[1]"),)
    assert result.image_evidence_ids == (evidence_id,)
    prompt = model.inputs[0]
    rendered = "\n".join(str(message.content) for message in prompt.messages)
    assert ledger.question in rendered
    assert evidence_id in rendered
    assert "A major triad has a root" in rendered


@pytest.mark.anyio
async def test_synthesis_service_rejects_output_that_cites_unknown_evidence() -> None:
    model = _StructuredModel(
        {
            "answer": "Unsupported.",
            "used_evidence_ids": ["document:foreign"],
            "citations": [{"evidence_id": "document:foreign", "label": "[1]"}],
        }
    )

    with pytest.raises(ValueError, match="existing evidence"):
        await EvidenceSynthesisService(model).synthesize(_ledger())


@pytest.mark.anyio
async def test_synthesis_service_rejects_image_claim_without_image_reference() -> None:
    ledger = _ledger()
    evidence_id = ledger.evidence[0].evidence_id
    without_image = EvidenceLedgerBuilder(
        "run-no-image",
        ledger.question,
        SelectionStrategy.PARAGRAPH_DIRECT,
    )
    without_image.add_document(
        source_ref="music-theory.md",
        chunk_id="chunk-1",
        paragraph_ref="paragraph-1",
        text="A major triad has a root, third, and fifth.",
        page=12,
    )
    no_image_ledger = without_image.build()
    no_image_id = no_image_ledger.evidence[0].evidence_id
    assert no_image_id == evidence_id
    model = _StructuredModel(
        {
            "answer": "A major triad has a root, third, and fifth.",
            "used_evidence_ids": [no_image_id],
            "citations": [{"evidence_id": no_image_id, "label": "[1]"}],
            "image_evidence_ids": [no_image_id],
        }
    )

    with pytest.raises(ValueError, match="evidence with images"):
        await EvidenceSynthesisService(model).synthesize(no_image_ledger)


@pytest.mark.anyio
async def test_synthesis_output_rejects_duplicate_ids_and_extra_fields() -> None:
    with pytest.raises(ValueError, match="unique"):
        SynthesisOutput.model_validate(
            {
                "answer": "A supported answer.",
                "used_evidence_ids": ["document:1", "document:1"],
            }
        )

    with pytest.raises(ValueError, match="extra"):
        SynthesisOutput.model_validate(
            {"answer": "A supported answer.", "unexpected": True}
        )


def test_synthesis_service_requires_structured_output_capable_model() -> None:
    with pytest.raises(TypeError, match="with_structured_output"):
        EvidenceSynthesisService(object())
