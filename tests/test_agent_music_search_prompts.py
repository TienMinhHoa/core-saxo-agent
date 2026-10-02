"""Proposed regressions for music document queries and citation few-shots.

Implementation is pending test-case approval. Provider doubles check transport
and prompt contracts; they do not measure a live model's language accuracy.
"""

from __future__ import annotations

import importlib
import json
import re
from types import SimpleNamespace

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from saxophone.agent.contracts import AgentQuestion, ChatHistoryMessage, RunBudget, SynthesisResult
from saxophone.agent.document_search import DocumentSearchResult
from saxophone.agent.evidence_selection import SelectionResult
from saxophone.agent.graph import AgentGraphDependencies
from saxophone.agent.orchestrator import MainAgent
from saxophone.agent.prompts import SYNTHESIS_PROMPT
from saxophone.retrieval.models import ChunkHit
from saxophone.retrieval.renderers import AnswerContextModel, SourceParagraph


def _citation_examples():
    prompt = SYNTHESIS_PROMPT.invoke({
        "question": "What is a musical scale?", "chat_history": "[]",
        "budget_status": "{}", "evidence_ledger": "No evidence.",
    })
    text = "\n".join(message.content for message in prompt.to_messages())
    blocks = re.findall(r"```json\s*(.*?)\s*```", text, flags=re.DOTALL)
    return [json.loads(block) for block in blocks]


def test_citation_few_shots_include_grounded_and_insufficient_answers():
    examples = _citation_examples()
    assert len(examples) >= 3
    assert any(example["evidence_sufficient"] for example in examples)
    assert any(not example["evidence_sufficient"] for example in examples)


def test_citation_few_shots_use_exact_bracketed_labels_and_matching_ids():
    examples = _citation_examples()
    assert examples
    for example in examples:
        labels = {citation["label"] for citation in example["citations"]}
        assert all(re.fullmatch(r"\[[1-9][0-9]*\]", label) for label in labels)
        assert set(re.findall(r"\[[0-9]+\]", example["answer"])) == labels
        assert set(example["used_evidence_ids"]) == {
            citation["evidence_id"] for citation in example["citations"]
        }


def test_citation_few_shots_cover_multiple_sources_and_uncited_internal_knowledge():
    examples = _citation_examples()
    assert any(len(example["citations"]) >= 2 for example in examples)
    assert any(
        not example["evidence_sufficient"]
        and not example["citations"] and not example["used_evidence_ids"]
        and not re.search(r"\[[0-9]+\]", example["answer"])
        for example in examples
    )


class _PlanningProvider:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _planner(provider):
    module = importlib.import_module("saxophone.agent.document_query_planning")
    return module.DocumentSearchQueryPlanner(provider)


@pytest.mark.anyio
async def test_doc_planner_generates_both_languages_in_one_model_call():
    queries = ["musical scale definition intervals tonic examples",
               "\u00e2m giai thang \u00e2m \u0111\u1ecbnh ngh\u0129a qu\u00e3ng n\u1ed1t ch\u1ee7 v\u00ed d\u1ee5"]
    provider = _PlanningProvider({"queries": queries})
    plan = await _planner(provider).plan(AgentQuestion("\u00e2m giai l\u00e0 g\u00ec"))
    assert list(plan.queries) == queries
    assert len(provider.calls) == 1
    system = provider.calls[0]["system_prompt"].lower()
    assert "music" in system and "chatbot" in system
    assert "english" in system and "user" in system and "language" in system
    assert "aspect" in system and "definition" in system and "example" in system


@pytest.mark.anyio
async def test_doc_planner_retry_receives_actual_document_text_and_previous_queries():
    provider = _PlanningProvider({"queries": [
        "scale definition tonic succession of intervals",
        "major minor scales note sequence examples",
    ]})
    evidence = "A scale is really nothing more than a specific succession of intervals."
    await _planner(provider).plan(
        AgentQuestion("\u00e2m giai l\u00e0 g\u00ec"),
        previous_queries=("\u00e2m giai l\u00e0 g\u00ec",),
        previous_evidence=(evidence,),
    )
    call = provider.calls[0]
    assert evidence in call["user_prompt"]
    assert "\u00e2m giai l\u00e0 g\u00ec" in call["user_prompt"]
    system = call["system_prompt"].lower()
    assert "document" in system and "language" in system
    assert "insufficient" in system and "refine" in system
    assert "only the document language" in system
    assert "do not add" in system
    assert "untrusted" in system


@pytest.mark.anyio
async def test_doc_planner_without_previous_hits_uses_one_provisional_language():
    provider = _PlanningProvider({"queries": ["music scale definition", "scale tonic intervals"]})
    await _planner(provider).plan(
        AgentQuestion("gam l\u00e0 g\u00ec"),
        previous_queries=("gam",), previous_evidence=(),
    )
    system = provider.calls[0]["system_prompt"].lower()
    assert "no document" in system and "english" in system
    assert "provisional" in system and "only the document language" in system


@pytest.mark.anyio
async def test_doc_planner_receives_history_and_preserves_music_notation():
    provider = _PlanningProvider({"queries": [
        "B-flat clarinet written key concert C major transposition",
        "clarinette si bemol tonalite ecrite do majeur transposition",
    ]})
    question = AgentQuestion(
        "And concert C major?", history=(ChatHistoryMessage(
            "user", "We are discussing a B-flat clarinet.",
        ),),
    )
    await _planner(provider).plan(question)
    call = provider.calls[0]
    assert "B-flat clarinet" in call["user_prompt"]
    assert question.question in call["user_prompt"]
    system = call["system_prompt"].lower()
    assert "preserve" in system and "notation" in system
    assert "do not answer" in system


@pytest.mark.anyio
async def test_doc_planner_handles_english_input_without_spending_duplicate_searches():
    provider = _PlanningProvider({"queries": ["music scale definition", "music scale definition"]})
    plan = await _planner(provider).plan(AgentQuestion("What is a scale?"))
    assert list(plan.queries) == ["music scale definition"]


@pytest.mark.anyio
@pytest.mark.parametrize("queries", [[], [""], ["one query"], ["q1", ""], ["q1", "q2", "q3"]])
async def test_doc_planner_rejects_empty_or_unbounded_plans(queries):
    with pytest.raises(ValueError):
        await _planner(_PlanningProvider({"queries": queries})).plan(AgentQuestion("scale?"))


@pytest.mark.anyio
async def test_doc_planner_provider_error_is_explicit():
    with pytest.raises(RuntimeError, match="planner unavailable"):
        await _planner(_PlanningProvider(RuntimeError("planner unavailable"))).plan(
            AgentQuestion("scale?")
        )


class _MainModel(BaseChatModel):
    @property
    def _llm_type(self):
        return "music-search-test"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, *args, **kwargs):
        raise AssertionError("Async only")

    async def _agenerate(self, messages, **kwargs):
        observations = [item for item in messages if isinstance(item, ToolMessage)]
        if not observations:
            name, args = "search_docs", {"query": "scale definition"}
        elif observations[-1].name == "search_docs":
            candidates = json.loads(observations[-1].content)["candidates"]
            name, args = "select_context", {
                "evidence_ids": [item["evidence_id"] for item in candidates]
            }
        else:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Done"))])
        message = AIMessage(content="", tool_calls=[{
            "name": name, "args": args, "id": f"music-{len(observations)}", "type": "tool_call",
        }])
        return ChatResult(generations=[ChatGeneration(message=message)])


@pytest.mark.anyio
@pytest.mark.parametrize("attempts", [1, 2])
async def test_docs_query_pair_costs_one_quota_and_merges_duplicate_evidence(attempts):
    paragraph = SourceParagraph(
        "p-scale", "music-theory-full", "Scales", (),
        "A scale is a succession of intervals starting from the tonic.",
        (), ("149",), (), "c-scale",
    )
    calls = []
    planning_calls = []

    class Docs:
        async def search(self, question, budget=None):
            calls.append(question)
            return DocumentSearchResult(
                question.question, hits=(ChunkHit("music-theory-full", "c-scale", 1, "topic-v1", {}),),
                paragraph_candidates=(paragraph,),
            )

    class Planner:
        async def plan(self, question, **kwargs):
            assert question.question == "\u00e2m giai l\u00e0 g\u00ec"
            planning_calls.append(kwargs)
            if len(planning_calls) > 1:
                assert paragraph.text in kwargs["previous_evidence"]
                return SimpleNamespace(queries=["scale tonic intervals", "scale major minor examples"])
            return SimpleNamespace(queries=["musical scale definition", "\u00e2m giai \u0111\u1ecbnh ngh\u0129a"])

    class Selector:
        async def select(self, request):
            assert request.question == "\u00e2m giai l\u00e0 g\u00ec"
            return SelectionResult("paragraph_direct", AnswerContextModel(
                (), (paragraph,), (paragraph.paragraph_ref,),
            ))

    class Synthesizer:
        calls = 0

        async def synthesize(self, ledger, **kwargs):
            self.calls += 1
            assert len(ledger.evidence) == 1
            return SynthesisResult("A scale is a succession of intervals.", evidence_sufficient=self.calls >= attempts)

    dependencies = AgentGraphDependencies(
        document_search=Docs(), paragraph_selector=Selector(), synthesizer=Synthesizer(),
        orchestrator_model=_MainModel(), document_query_planner=Planner(),
    )
    budget = RunBudget(max_document_search_calls=3, max_web_search_calls=2)
    result = await MainAgent(dependencies=dependencies).run(
        AgentQuestion("\u00e2m giai l\u00e0 g\u00ec", filters={"document_ref": "music-theory-full"}),
        budget=budget,
    )
    assert result.error is None, result.error
    expected = [
        "musical scale definition", "\u00e2m giai \u0111\u1ecbnh ngh\u0129a",
    ]
    if attempts == 2:
        expected.extend(["scale tonic intervals", "scale major minor examples"])
    assert [question.question for question in calls] == expected
    assert all(dict(question.filters) == {"document_ref": "music-theory-full"} for question in calls)
    assert budget.snapshot().document_search_calls == attempts
    assert budget.snapshot().web_search_calls == 0


def test_merge_query_languages_interleaves_hits_and_keeps_paragraphs_in_scope():
    from saxophone.agent.react_pipeline import _merge_document_results

    def result(query, prefix):
        hits = tuple(ChunkHit("music-theory-full", f"{prefix}-{index}", index, "topic-v1", {})
                     for index in (1, 2))
        paragraphs = tuple(SourceParagraph(
            f"p-{hit.chunk_ref}", "music-theory-full", "Scales", (),
            f"Text for {hit.chunk_ref}", (), ("149",), (), hit.chunk_ref,
        ) for hit in hits)
        return DocumentSearchResult(query, hits=hits, paragraph_candidates=paragraphs)

    merged = _merge_document_results([result("English scale", "en"), result("gam", "vi")], 2)
    assert [hit.chunk_ref for hit in merged.hits] == ["en-1", "vi-1"]
    assert [hit.rank for hit in merged.hits] == [1, 2]
    assert {paragraph.chunk_id for paragraph in merged.paragraph_candidates} == {"en-1", "vi-1"}


def test_merge_empty_queries_preserves_no_hits_status():
    from saxophone.agent.react_pipeline import _merge_document_results

    merged = _merge_document_results([
        DocumentSearchResult("scale definition"), DocumentSearchResult("gam"),
    ], 10)
    assert merged.hits == () and merged.paragraph_candidates == ()
    assert merged.status.value == "no_hits"
