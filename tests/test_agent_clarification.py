from __future__ import annotations

from dataclasses import dataclass

import pytest

from saxophone.agent.contracts import (
    AgentOutcome,
    AgentQuestion,
    ClarificationCandidate,
    RunBudget,
)
from saxophone.agent.document_search import DocumentSearchResult, DocumentSearchStatus
from saxophone.agent.graph import AgentGraphDependencies, build_agent_graph
from saxophone.agent.policies import ClarificationPolicy
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.renderers import SourceParagraph


def _ready_result() -> DocumentSearchResult:
    hit = ChunkHit(
        "music.md",
        "chunk-1",
        1,
        "retrieval-v1",
        {"document_ref": "music-book"},
        semantic_score=0.9,
    )
    paragraph = SourceParagraph(
        "paragraph-1",
        "music.md",
        "Triads",
        (),
        "A triad has three notes.",
        (),
        ("1",),
        (),
        "chunk-1",
    )
    return DocumentSearchResult(
        "Which triad?",
        (hit,),
        (paragraph,),
        status=DocumentSearchStatus.READY,
    )


def test_clarification_candidate_validates_label_and_confidence() -> None:
    candidate = ClarificationCandidate("Major triad", 0.82)

    assert candidate.label == "Major triad"
    assert candidate.confidence == pytest.approx(0.82)

    with pytest.raises(ValueError):
        ClarificationCandidate("", 0.82)
    with pytest.raises(ValueError):
        ClarificationCandidate("Major triad", 1.1)


def test_clarification_policy_requests_choice_for_competing_supported_meanings() -> None:
    policy = ClarificationPolicy()
    request = policy(
        {
            "question": AgentQuestion("Which triad?"),
            "document_result": _ready_result(),
            "clarification_candidates": (
                ClarificationCandidate("Major triad", 0.82),
                ClarificationCandidate("Minor triad", 0.80),
            ),
        }
    )

    assert request is not None
    assert request.question == "Which triad?"
    assert request.options == ("Major triad", "Minor triad")
    assert request.reason_code == "multiple_supported_interpretations"


def test_clarification_policy_does_not_interrupt_a_clear_interpretation() -> None:
    policy = ClarificationPolicy()

    request = policy(
        {
            "question": AgentQuestion("What is a major triad?"),
            "document_result": _ready_result(),
            "clarification_candidates": (
                ClarificationCandidate("Major triad", 0.92),
                ClarificationCandidate("Minor triad", 0.55),
            ),
        }
    )

    assert request is None


def test_clarification_policy_does_not_replace_web_fallback_when_local_search_is_empty() -> None:
    policy = ClarificationPolicy()
    result = DocumentSearchResult("Which triad?", status=DocumentSearchStatus.NO_HITS)

    request = policy(
        {
            "question": AgentQuestion("Which triad?"),
            "document_result": result,
            "clarification_candidates": (
                ClarificationCandidate("Major triad", 0.8),
                ClarificationCandidate("Minor triad", 0.8),
            ),
        }
    )

    assert request is None


@dataclass
class _DocumentSearch:
    result: DocumentSearchResult

    async def search(self, question: AgentQuestion, budget: RunBudget) -> DocumentSearchResult:
        return self.result


@dataclass
class _Synthesizer:
    calls: int = 0

    async def synthesize(self, ledger):
        self.calls += 1
        raise AssertionError("clarification must stop before synthesis")


@pytest.mark.anyio
async def test_graph_routes_policy_clarification_without_synthesis() -> None:
    synthesizer = _Synthesizer()
    graph = build_agent_graph(
        AgentGraphDependencies(
            document_search=_DocumentSearch(_ready_result()),
            synthesizer=synthesizer,
            clarification_policy=ClarificationPolicy(),
        )
    )

    state = await graph.ainvoke(
        {
            "run_id": "run-clarification-policy",
            "question": AgentQuestion("Which triad?"),
            "budget": RunBudget(),
            "clarification_candidates": (
                ClarificationCandidate("Major triad", 0.82),
                ClarificationCandidate("Minor triad", 0.81),
            ),
        },
        config={"configurable": {"thread_id": "run-clarification-policy"}},
    )

    assert state["outcome"] is AgentOutcome.NEEDS_CLARIFICATION
    assert state["clarification"].options == ("Major triad", "Minor triad")
    assert synthesizer.calls == 0
