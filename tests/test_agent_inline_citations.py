from __future__ import annotations

from dataclasses import dataclass, field
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda

from saxophone.agent.contracts import AgentOutcome, Citation, RunBudget, SynthesisResult
from saxophone.agent.evidence import EvidenceLedgerBuilder
from saxophone.agent.orchestrator import AgentRunResult
from saxophone.agent.state import AgentStage
from saxophone.agent.streaming import AgentRunManager
from saxophone.agent.synthesis import EvidenceSynthesisService
from saxophone.interfaces.api import build_agent_chat_router


def _ledger():
    builder = EvidenceLedgerBuilder("inline-citations", "How does alto saxophone transpose?", "paragraph_direct")
    builder.add_document(
        source_ref="music-theory-full", chunk_id="c-alto", paragraph_ref="p-alto",
        text="Alto saxophone is an E-flat transposing instrument.", page=42,
    )
    builder.add_web(
        title="Alto saxophone transposition", url="https://example.test/alto",
        snippet="Concert C major is written A major for alto saxophone.", retrieved_at="2026-10-02",
    )
    return builder.build()


@dataclass
class _Model:
    response: dict
    prompts: list = field(default_factory=list)

    def with_structured_output(self, schema):
        def invoke(prompt):
            self.prompts.append(prompt)
            return self.response
        return RunnableLambda(invoke)


def _output(ledger, *, answer="Alto is in E-flat [1]. Concert C is written A [2].", labels=("[1]", "[2]")):
    ids = [item.evidence_id for item in ledger.evidence]
    return {
        "answer": answer, "evidence_sufficient": True, "used_evidence_ids": ids,
        "citations": [{"evidence_id": evidence_id, "label": label} for evidence_id, label in zip(ids, labels)],
    }


@pytest.mark.anyio
async def test_prompt_assigns_numeric_labels_and_requests_inline_citations():
    ledger = _ledger()
    model = _Model(_output(ledger))
    await EvidenceSynthesisService(model).synthesize(ledger)
    messages = model.prompts[0].to_messages()
    system = messages[0].content.lower()
    assert "inline" in system
    assert "[1]" in system and "[2]" in system
    assert "claim" in system
    evidence_prompt = messages[1].content
    assert "citation_label: [1]" in evidence_prompt
    assert "citation_label: [2]" in evidence_prompt


@pytest.mark.anyio
async def test_valid_inline_citations_keep_their_evidence_mapping():
    ledger = _ledger()
    output = _output(ledger)
    result = await EvidenceSynthesisService(_Model(output)).synthesize(ledger)
    assert result.answer == output["answer"]
    assert result.citations == tuple(Citation(item.evidence_id, f"[{index}]")
                                     for index, item in enumerate(ledger.evidence, start=1))


@pytest.mark.anyio
async def test_nonsequential_numeric_labels_are_renumbered_in_answer_and_sources_together():
    ledger = _ledger()
    output = _output(ledger, answer="Alto is in E-flat [10]. Concert C is written A [7]. Again [10].",
                     labels=("[10]", "[7]"))
    result = await EvidenceSynthesisService(_Model(output)).synthesize(ledger)
    assert result.answer == "Alto is in E-flat [1]. Concert C is written A [2]. Again [1]."
    assert [citation.label for citation in result.citations] == ["[1]", "[2]"]
    assert [citation.evidence_id for citation in result.citations] == [item.evidence_id for item in ledger.evidence]


@pytest.mark.anyio
async def test_swapped_numeric_labels_are_replaced_without_cascading_replacements():
    ledger = _ledger()
    output = _output(ledger, answer="First source [2]; second source [1].", labels=("[2]", "[1]"))
    result = await EvidenceSynthesisService(_Model(output)).synthesize(ledger)
    assert result.answer == "First source [1]; second source [2]."


@pytest.mark.anyio
async def test_multiple_citations_can_follow_one_claim():
    ledger = _ledger()
    result = await EvidenceSynthesisService(_Model(_output(
        ledger, answer="Alto is in E-flat; concert C is written A [1][2].",
    ))).synthesize(ledger)
    assert result.answer.endswith("[1][2].")


@pytest.mark.anyio
@pytest.mark.parametrize("answer", [
    "Alto is in E-flat. Concert C is written A.",
    "Alto is in E-flat [1]. Concert C is written A [99].",
    "Alto is in E-flat [1].",
], ids=["missing-inline-labels", "unknown-label", "unused-citation"])
async def test_synthesis_rejects_missing_unknown_or_unused_inline_citations(answer):
    ledger = _ledger()
    with pytest.raises(ValueError):
        await EvidenceSynthesisService(_Model(_output(ledger, answer=answer))).synthesize(ledger)


@pytest.mark.anyio
async def test_synthesis_rejects_titles_used_as_citation_labels():
    ledger = _ledger()
    with pytest.raises(ValueError):
        await EvidenceSynthesisService(_Model(_output(
            ledger, labels=("Music theory, page 42", "Alto transposition guide"),
        ))).synthesize(ledger)


@pytest.mark.anyio
async def test_no_evidence_response_does_not_invent_citations():
    ledger = EvidenceLedgerBuilder("no-inline-evidence", "Unknown subject", "paragraph_direct").build()
    result = await EvidenceSynthesisService(_Model({
        "answer": "There is not enough source evidence to answer.", "evidence_sufficient": False, "used_evidence_ids": [], "citations": [],
    })).synthesize(ledger)
    assert result.citations == ()
    assert "[1]" not in result.answer


@pytest.mark.anyio
async def test_empty_evidence_cannot_support_an_inline_source():
    ledger = EvidenceLedgerBuilder("no-source", "Unknown subject", "paragraph_direct").build()
    with pytest.raises(ValueError):
        await EvidenceSynthesisService(_Model({
            "answer": "An unsupported fact [1].", "evidence_sufficient": False, "used_evidence_ids": [], "citations": [],
        })).synthesize(ledger)


def _app():
    ledger = _ledger()
    result = AgentRunResult(
        ledger.run_id, AgentOutcome.ANSWERED, AgentStage.COMPLETED, RunBudget(),
        answer="Alto is in E-flat [1]. Concert C is written A [2].", ledger=ledger,
        synthesis=SynthesisResult(
            "Alto is in E-flat [1]. Concert C is written A [2].",
            tuple(item.evidence_id for item in ledger.evidence),
            tuple(Citation(item.evidence_id, f"[{index}]") for index, item in enumerate(ledger.evidence, start=1)),
        ),
    )

    class Runner:
        async def run(self, question, *, run_id, callbacks=None):
            return result

    app = FastAPI()
    app.include_router(build_agent_chat_router(agent_runner=Runner(), agent_run_manager=AgentRunManager()))
    return app


@pytest.mark.parametrize("route", ["/agent/chat/messages", "/agent/chat/stream"])
def test_api_exposes_matching_numeric_sources_with_document_location_and_web_url(route):
    response = TestClient(_app()).post(route, json={"question": "How does alto transpose?"})
    assert response.status_code == 200
    if route.endswith("/stream"):
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        payload = next(event["result"] for event in events if event["type"] == "run_result")
    else:
        payload = response.json()
    assert "[1]" in payload["answer"] and "[2]" in payload["answer"]
    assert [source["citation"] for source in payload["sources"]] == ["[1]", "[2]"]
    assert payload["sources"][0]["source"] == "music-theory-full"
    assert payload["sources"][0]["page_start"] == 42
    assert payload["sources"][1]["url"] == "https://example.test/alto"
