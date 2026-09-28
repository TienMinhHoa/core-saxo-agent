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
from saxophone.agent.policies import run_with_budget
from saxophone.agent.synthesis import EvidenceSynthesisService
from saxophone.interfaces.api import _agent_run_sources
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.renderers import (
    AnswerContextModel,
    SelectedConceptRole,
    SourceParagraph,
)
from saxophone.tagging.models import ContentRole, ParagraphConceptRole


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


class _ImageStructuredModel(_StructuredModel):
    def with_structured_output(self, _schema: object) -> RunnableLambda:
        async def respond(payload: object) -> dict[str, object]:
            rendered = payload.to_string() if hasattr(payload, "to_string") else str(payload)
            evidence_id = re.search(r"evidence_id: (\S+)", rendered)
            assert evidence_id is not None
            return {
                "answer": "Grounded answer with an illustration",
                "used_evidence_ids": [evidence_id.group(1)],
                "citations": [{"evidence_id": evidence_id.group(1), "label": "[1]"}],
                "image_evidence_ids": [evidence_id.group(1)],
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
class _FailingDocumentSearch:
    error: BaseException
    calls: list[tuple[AgentQuestion, RunBudget]] = field(default_factory=list)

    async def search(
        self, question: AgentQuestion, budget: RunBudget
    ) -> DocumentSearchResult:
        self.calls.append((question, budget))
        raise self.error


@dataclass
class _BudgetedNoHitDocumentSearch:
    calls: int = 0

    async def search(
        self, question: AgentQuestion, budget: RunBudget
    ) -> DocumentSearchResult:
        async def operation() -> DocumentSearchResult:
            self.calls += 1
            return DocumentSearchResult(
                question.question,
                status=DocumentSearchStatus.NO_HITS,
            )

        return await run_with_budget(budget, "document_search", operation)


@dataclass
class _BudgetedWebSearch:
    calls: int = 0

    async def search(
        self, question: AgentQuestion, budget: RunBudget
    ) -> WebSearchResult:
        async def operation() -> WebSearchResult:
            self.calls += 1
            return WebSearchResult(
                question.question,
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

        return await run_with_budget(budget, "web_search", operation)


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
class _ConceptSelector:
    calls: list[object] = field(default_factory=list)

    async def select(self, request: object) -> object:
        from saxophone.agent.contracts import SelectionStrategy
        from saxophone.agent.evidence_selection import SelectionResult

        self.calls.append(request)
        paragraph = request.search_result.paragraph_candidates[0]
        return SelectionResult(
            SelectionStrategy.CONCEPT_ROLE,
            AnswerContextModel(
                (
                    SelectedConceptRole(
                        "Major triad",
                        ContentRole.DEFINITION.value,
                        (paragraph.paragraph_ref,),
                        (),
                    ),
                ),
                (paragraph,),
                (paragraph.paragraph_ref,),
            ),
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


@dataclass
class _CountingSynthesizer:
    calls: int = 0

    async def synthesize(self, ledger: object) -> object:
        self.calls += 1
        raise AssertionError("ambiguous evidence must stop before synthesis")


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
async def test_pipeline_routes_relation_rich_results_to_concept_role_strategy() -> None:
    paragraph = _paragraph()
    document = _DocumentSearch(
        DocumentSearchResult(
            "What is a major triad?",
            (_hit(),),
            (paragraph,),
            relations=(
                ParagraphConceptRole(
                    paragraph.paragraph_ref,
                    "Major triad",
                    ContentRole.DEFINITION,
                ),
            ),
            status=DocumentSearchStatus.READY,
        )
    )
    selector = _ConceptSelector()
    synthesizer = _ConfigAwareSynthesizer()
    agent = MainAgent(
        document_search=document,
        concept_selector=selector,
        synthesizer=synthesizer,
    )

    result = await agent.run("What is a major triad?", run_id="pipeline-concept-role")

    assert result.outcome is AgentOutcome.ANSWERED
    assert result.ledger is not None
    assert result.ledger.selected_strategy.value == "concept_role"
    assert len(selector.calls) == 1


@pytest.mark.anyio
async def test_pipeline_returns_clarification_without_synthesis_for_ambiguous_evidence() -> None:
    paragraph = _paragraph()
    document = _DocumentSearch(
        DocumentSearchResult(
            "Which triad?",
            (_hit(),),
            (paragraph,),
            status=DocumentSearchStatus.READY,
        )
    )
    synthesizer = _CountingSynthesizer()
    agent = MainAgent(
        document_search=document,
        paragraph_selector=_Selector(),
        synthesizer=synthesizer,
        clarification_policy=lambda _state: (
            "Which triad do you mean?",
            ("major", "minor"),
        ),
    )

    result = await agent.run("Which triad?", run_id="pipeline-clarification")

    assert result.outcome is AgentOutcome.NEEDS_CLARIFICATION
    assert result.clarification is not None
    assert result.clarification.options == ("major", "minor")
    assert result.answer is None
    assert synthesizer.calls == 0


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
async def test_pipeline_returns_structured_failure_when_document_search_errors() -> None:
    document = _FailingDocumentSearch(RuntimeError("document backend unavailable"))
    web = _WebSearch(
        WebSearchResult(
            "What is rhythm?",
            (),
            status="ready",
        )
    )
    agent = MainAgent(document_search=document, web_search=web)

    result = await agent.run("What is rhythm?", run_id="pipeline-document-error")

    assert result.outcome is AgentOutcome.FAILED
    assert result.answer is None
    assert result.error == "document backend unavailable"
    assert len(document.calls) == 1
    assert web.calls == []


@pytest.mark.anyio
async def test_pipeline_stops_before_web_when_shared_budget_is_exhausted() -> None:
    document = _BudgetedNoHitDocumentSearch()
    web = _BudgetedWebSearch()
    budget = RunBudget(max_tool_calls=1)
    agent = MainAgent(document_search=document, web_search=web)

    result = await agent.run(
        "What is rhythm?",
        run_id="pipeline-budget-exhausted",
        budget=budget,
    )

    assert result.outcome is AgentOutcome.BUDGET_EXHAUSTED
    assert result.answer is None
    assert result.error == "budget exhausted for web_search: max_tool_calls"
    assert document.calls == 1
    assert web.calls == 0
    assert budget.snapshot().tool_calls == 1
    assert budget.snapshot().web_search_calls == 0
    assert result.state is not None
    assert result.state["reason_code"] == "max_tool_calls"


@pytest.mark.anyio
async def test_pipeline_returns_images_only_for_cited_evidence() -> None:
    paragraph = SourceParagraph(
        "paragraph-1",
        "music.md",
        "Major triads",
        (),
        "A major triad has a root, third, and fifth.",
        ("Major triad -> Definition",),
        ("121",),
        ("images/major-triad.png",),
        "chunk-1",
    )
    document = _DocumentSearch(
        DocumentSearchResult(
            "What is a major triad?",
            (_hit(),),
            (paragraph,),
            status=DocumentSearchStatus.READY,
        )
    )
    agent = MainAgent(
        document_search=document,
        paragraph_selector=_Selector(),
        synthesizer=EvidenceSynthesisService(_ImageStructuredModel()),
    )

    result = await agent.run("What is a major triad?", run_id="pipeline-image")

    assert result.outcome is AgentOutcome.ANSWERED
    assert result.ledger is not None
    assert result.synthesis is not None
    evidence_id = result.ledger.evidence[0].evidence_id
    assert result.synthesis.image_evidence_ids == (evidence_id,)
    sources = _agent_run_sources(result)
    assert len(sources) == 1
    assert sources[0].image_refs == paragraph.image_refs


@pytest.mark.anyio
async def test_pipeline_does_not_project_images_for_cited_evidence_without_images() -> None:
    paragraph = _paragraph()
    document = _DocumentSearch(
        DocumentSearchResult(
            "What is a major triad?",
            (_hit(),),
            (paragraph,),
            status=DocumentSearchStatus.READY,
        )
    )
    agent = MainAgent(
        document_search=document,
        paragraph_selector=_Selector(),
        synthesizer=EvidenceSynthesisService(_StructuredModel()),
    )

    result = await agent.run("What is a major triad?", run_id="pipeline-no-image")

    assert result.outcome is AgentOutcome.ANSWERED
    assert result.synthesis is not None
    assert result.synthesis.image_evidence_ids == ()
    sources = _agent_run_sources(result)
    assert len(sources) == 1
    assert sources[0].image_refs == ()


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
