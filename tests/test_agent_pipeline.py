from __future__ import annotations

import re
from dataclasses import dataclass, field

import pytest
from langchain_core.runnables import RunnableLambda

from saxophone.agent.contracts import (
    AgentOutcome,
    AgentQuestion,
    RunBudget,
    WebSearchItem,
    WebSearchResult,
)
from saxophone.agent.document_search import DocumentSearchResult, DocumentSearchStatus
from saxophone.agent.langchain_callbacks import AgentTracingCallbackHandler
from saxophone.agent.orchestrator import MainAgent
from saxophone.agent.synthesis import EvidenceSynthesisService
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.renderers import SourceParagraph


def _paragraph() -> SourceParagraph:
    return SourceParagraph(
        "paragraph-1",
        "music.md",
        "Major triads",
        (),
        "A major triad has a root, third, and fifth.",
        ("Major triad -> Definition",),
        ("121",),
        (),
        "chunk-1",
    )


def _hit() -> ChunkHit:
    return ChunkHit(
        "music.md",
        "chunk-1",
        1,
        "retrieval-v1",
        {"document_ref": "music-book", "source_version": "source-v1"},
        semantic_score=0.9,
    )


class _StructuredModel:
    def with_structured_output(self, _schema: object) -> RunnableLambda:
        async def respond(payload: object) -> dict[str, object]:
            rendered = payload.to_string() if hasattr(payload, "to_string") else str(payload)
            evidence_id = re.search(r"evidence_id: (\S+)", rendered)
            assert evidence_id is not None
            return {
                "answer": "Grounded answer",
                "used_evidence_ids": [evidence_id.group(1)],
                "citations": [{"evidence_id": evidence_id.group(1), "label": "[1]"}],
            }

        return RunnableLambda(respond)


@dataclass
class _DocumentSearch:
    result: DocumentSearchResult
    calls: list[tuple[AgentQuestion, RunBudget]] = field(default_factory=list)

    async def search(
        self, question: AgentQuestion, budget: RunBudget
    ) -> DocumentSearchResult:
        self.calls.append((question, budget))
        return self.result


@dataclass
class _WebSearch:
    result: WebSearchResult
    calls: list[tuple[AgentQuestion, RunBudget]] = field(default_factory=list)

    async def search(
        self, question: AgentQuestion, budget: RunBudget
    ) -> WebSearchResult:
        self.calls.append((question, budget))
        return self.result


class _Selector:
    async def select(self, request: object) -> object:
        from saxophone.agent.contracts import SelectionStrategy
        from saxophone.agent.evidence_selection import SelectionResult
        from saxophone.retrieval.renderers import AnswerContextModel

        result = request.search_result
        paragraph = result.paragraph_candidates[0]
        return SelectionResult(
            SelectionStrategy.PARAGRAPH_DIRECT,
            AnswerContextModel((), (paragraph,), (paragraph.paragraph_ref,)),
        )


@dataclass
class _ConfigAwareSynthesizer:
    config: object | None = None

    async def synthesize(self, ledger: object, *, config: object | None = None) -> object:
        self.config = config
        evidence_id = ledger.evidence[0].evidence_id
        from saxophone.agent.contracts import Citation, SynthesisResult

        return SynthesisResult(
            "Grounded answer",
            (evidence_id,),
            (Citation(evidence_id, "[1]"),),
        )


@pytest.mark.anyio
async def test_pipeline_uses_local_evidence_without_web_fallback() -> None:
    paragraph = _paragraph()
    document = _DocumentSearch(
        DocumentSearchResult(
            "What is a major triad?",
            (_hit(),),
            (paragraph,),
            status=DocumentSearchStatus.READY,
        )
    )
    web = _WebSearch(
        WebSearchResult(
            "What is a major triad?",
            (WebSearchItem("unused", "https://example.test/unused", "unused", "2026-09-29"),),
            status="ready",
        )
    )
    agent = MainAgent(
        document_search=document,
        paragraph_selector=_Selector(),
        web_search=web,
        synthesizer=EvidenceSynthesisService(_StructuredModel()),
    )

    result = await agent.run("What is a major triad?", run_id="pipeline-local")

    assert result.outcome is AgentOutcome.ANSWERED
    assert result.answer == "Grounded answer"
    assert len(document.calls) == 1
    assert web.calls == []


@pytest.mark.anyio
async def test_pipeline_uses_web_once_when_local_evidence_has_no_hits() -> None:
    document = _DocumentSearch(
        DocumentSearchResult(
            "What is rhythm?",
            status=DocumentSearchStatus.NO_HITS,
        )
    )
    web = _WebSearch(
        WebSearchResult(
            "What is rhythm?",
            (
                WebSearchItem(
                    "Rhythm",
                    "https://example.test/rhythm",
                    "Rhythm is organized movement in time.",
                    "2026-09-29",
                ),
            ),
            status="ready",
        )
    )
    agent = MainAgent(
        document_search=document,
        web_search=web,
        synthesizer=EvidenceSynthesisService(_StructuredModel()),
    )

    result = await agent.run("What is rhythm?", run_id="pipeline-web")

    assert result.outcome is AgentOutcome.ANSWERED
    assert len(web.calls) == 1
    assert result.ledger is not None
    assert result.ledger.evidence[0].url == "https://example.test/rhythm"


@pytest.mark.anyio
async def test_pipeline_forwards_runnable_config_to_synthesis() -> None:
    paragraph = _paragraph()
    document = _DocumentSearch(
        DocumentSearchResult(
            "What is a major triad?",
            (_hit(),),
            (paragraph,),
            status=DocumentSearchStatus.READY,
        )
    )
    synthesizer = _ConfigAwareSynthesizer()
    agent = MainAgent(
        document_search=document,
        paragraph_selector=_Selector(),
        synthesizer=synthesizer,
    )

    result = await agent.run("What is a major triad?", run_id="pipeline-config")

    assert result.outcome is AgentOutcome.ANSWERED
    assert isinstance(synthesizer.config, dict)
    callbacks = synthesizer.config.get("callbacks")
    handlers = getattr(callbacks, "handlers", callbacks or ())
    assert any(
        isinstance(callback, AgentTracingCallbackHandler)
        for callback in handlers
    )
