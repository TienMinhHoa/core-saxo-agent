from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from saxophone.agent.contracts import (
    AgentOutcome,
    AgentQuestion,
    Citation,
    ClarificationRequest,
    EvidenceItem,
    EvidenceLedger,
    EvidenceSourceType,
    SelectionStrategy,
)


def _document_evidence(
    evidence_id: str = "e-1",
    *,
    image_refs: tuple[str, ...] = (),
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_type=EvidenceSourceType.DOCUMENT,
        chunk="chunk-1",
        paragraph="paragraph-1",
        text="A supported paragraph.",
        page=1,
        image_refs=image_refs,
    )


def test_agent_question_normalizes_and_freezes_filters() -> None:
    question = AgentQuestion(
        "  What is harmony?  ",
        filters={"document_ref": "music"},
        context_limit=500,
    )

    assert question.question == "What is harmony?"
    assert question.context_limit == 500
    assert question.filters == {"document_ref": "music"}
    with pytest.raises(TypeError):
        question.filters["document_ref"] = "other"  # type: ignore[index]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"question": ""},
        {"question": "question", "context_limit": 0},
        {"question": "question", "filters": {"": "value"}},
    ],
)
def test_agent_question_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        AgentQuestion(**kwargs)


def test_evidence_item_supports_document_aliases_and_safe_images() -> None:
    evidence = _document_evidence(image_refs=("images/harmony.png",))

    assert evidence.chunk_id == "chunk-1"
    assert evidence.paragraph_ref == "paragraph-1"
    assert evidence.page_start == 1
    assert evidence.page_end == 1
    assert evidence.source_type is EvidenceSourceType.DOCUMENT


@pytest.mark.parametrize(
    "kwargs",
    [
        {"evidence_id": "", "source_type": "document", "text": "text"},
        {
            "evidence_id": "e-1",
            "source_type": "document",
            "chunk": "chunk-1",
            "paragraph": "paragraph-1",
            "text": "text",
            "image_refs": ("../secret.png",),
        },
        {
            "evidence_id": "e-1",
            "source_type": "web",
            "text": "web text",
        },
    ],
)
def test_evidence_item_rejects_invalid_source_contract(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        EvidenceItem(**kwargs)


def test_ledger_rejects_duplicate_evidence_and_dangling_citations() -> None:
    evidence = _document_evidence()

    with pytest.raises(ValueError, match="unique"):
        EvidenceLedger(
            run_id="run-1",
            question="What is harmony?",
            selected_strategy=SelectionStrategy.PARAGRAPH_DIRECT,
            evidence=(evidence, evidence),
        )

    with pytest.raises(ValueError, match="evidence"):
        EvidenceLedger(
            run_id="run-1",
            question="What is harmony?",
            selected_strategy=SelectionStrategy.PARAGRAPH_DIRECT,
            evidence=(evidence,),
            citations=(Citation("missing", "[1]"),),
        )


def test_ledger_rejects_image_evidence_without_images_and_is_immutable() -> None:
    with pytest.raises(ValueError, match="image"):
        EvidenceLedger(
            run_id="run-1",
            question="What is harmony?",
            selected_strategy="paragraph_direct",
            evidence=(_document_evidence(),),
            used_evidence_ids=("e-1",),
            image_evidence_ids=("e-1",),
        )

    ledger = EvidenceLedger(
        run_id="run-1",
        question="What is harmony?",
        selected_strategy="paragraph_direct",
        evidence=(_document_evidence(image_refs=("images/harmony.png",)),),
        used_evidence_ids=("e-1",),
        citations=(Citation("e-1", "[1]"),),
        image_evidence_ids=("e-1",),
    )

    with pytest.raises(FrozenInstanceError):
        ledger.run_id = "run-2"  # type: ignore[misc]


def test_clarification_request_and_outcome_contract() -> None:
    request = ClarificationRequest(
        question="Which formula do you mean?",
        options=("I-IV-V", "Another formula"),
        reason_code="multiple_supported_interpretations",
    )

    assert request.options == ("I-IV-V", "Another formula")
    assert AgentOutcome.NEEDS_CLARIFICATION.value == "needs_clarification"
