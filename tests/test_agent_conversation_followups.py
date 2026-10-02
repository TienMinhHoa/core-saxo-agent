"""Prompt and output-boundary checks for contextual conversational follow-ups."""

from __future__ import annotations

from dataclasses import replace

import pytest
from langchain_core.runnables import RunnableLambda

from saxophone.agent.contracts import ChatHistoryMessage
from saxophone.agent.evidence import EvidenceLedgerBuilder
from saxophone.agent.prompts import SYNTHESIS_SYSTEM_PROMPT
from saxophone.agent.synthesis import EvidenceSynthesisService


def test_synthesis_prefers_one_specific_optional_follow_up_after_the_answer():
    prompt = SYNTHESIS_SYSTEM_PROMPT.lower()
    assert "follow-up question" in prompt
    assert "at most one" in prompt
    assert "after answering" in prompt
    assert "specific to the topic" in prompt
    assert "example" in prompt
    assert "deeper explanation" in prompt
    assert "practical application" in prompt


def test_follow_up_policy_uses_history_and_respects_declined_or_brief_requests():
    prompt = SYNTHESIS_SYSTEM_PROMPT.lower()
    assert "avoid repeating" in prompt
    assert "declined" in prompt
    assert "brief" in prompt
    assert "no follow-up" in prompt
    assert "chat history" in prompt


def test_follow_up_policy_does_not_compete_with_clarification_or_add_unsupported_claims():
    prompt = SYNTHESIS_SYSTEM_PROMPT.lower()
    assert "clarification question" in prompt
    assert "error" in prompt
    assert "do not promise" in prompt
    assert "unsupported facts" in prompt


class _Model:
    def __init__(self, output):
        self.output = output
        self.prompts = []

    def with_structured_output(self, schema):
        def respond(prompt):
            self.prompts.append(prompt.to_string())
            return self.output
        return RunnableLambda(respond)


def _ledger():
    builder = EvidenceLedgerBuilder("follow-up", "What does 145 mean?", "paragraph_direct")
    builder.add_web(title="I IV V", url="https://example.test/145",
                    snippet="145 denotes chords on scale degrees I, IV, and V.", retrieved_at="2026-10-02")
    return builder.build()


@pytest.mark.anyio
async def test_grounded_answer_keeps_citation_and_contextual_follow_up_together():
    ledger = _ledger()
    evidence_id = ledger.evidence[0].evidence_id
    answer = "145 denotes I, IV, and V [1].\n\nWould you like an example in C major?"
    model = _Model({
        "answer": answer, "evidence_sufficient": True,
        "used_evidence_ids": [evidence_id], "citations": [{"evidence_id": evidence_id, "label": "[1]"}],
    })
    result = await EvidenceSynthesisService(model).synthesize(ledger)
    assert result.answer == answer
    assert result.citations[0].label == "[1]"
    assert result.used_evidence_ids == (evidence_id,)
    assert "follow-up question" in model.prompts[0].lower()


@pytest.mark.anyio
async def test_internal_answer_can_offer_an_example_without_inventing_a_source():
    ledger = EvidenceLedgerBuilder("follow-up-empty", "What does 145 mean?", "paragraph_direct").build()
    answer = "145 usually means I, IV, and V.\n\nWould you like a practical chord example?"
    model = _Model({"answer": answer, "evidence_sufficient": False,
                    "used_evidence_ids": [], "citations": []})
    result = await EvidenceSynthesisService(model).synthesize(ledger)
    assert result.answer.endswith(answer)
    assert "kiến thức nội tại" in result.answer
    assert result.citations == ()
    assert result.used_evidence_ids == ()


@pytest.mark.anyio
async def test_declined_offer_is_forwarded_in_history_and_no_question_is_forced_by_application():
    ledger = replace(_ledger(), history=(
        ChatHistoryMessage("assistant", "Would you like a chord example?"),
        ChatHistoryMessage("user", "No examples, just a brief definition with no follow-up."),
    ))
    evidence_id = ledger.evidence[0].evidence_id
    answer = "145 denotes I, IV, and V [1]."
    model = _Model({"answer": answer, "evidence_sufficient": True,
                    "used_evidence_ids": [evidence_id],
                    "citations": [{"evidence_id": evidence_id, "label": "[1]"}]})
    result = await EvidenceSynthesisService(model).synthesize(ledger)
    assert "No examples, just a brief definition with no follow-up." in model.prompts[0]
    assert result.answer == answer
    assert "?" not in result.answer
