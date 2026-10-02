from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from saxophone.agent.contracts import (
    AgentOutcome,
    Citation,
    EvidenceLedger,
    RunBudget,
    SelectionStrategy,
    SynthesisResult,
)
from saxophone.agent.evidence import EvidenceLedgerBuilder
from saxophone.agent.orchestrator import AgentRunResult
from saxophone.agent.state import AgentStage
from saxophone.chat.service import (
    AnswerSource,
    GroundedAnswerResponse,
    GroundedAnswerService,
    GroundedAnswerStatus,
)
from saxophone.interfaces.api import build_agent_chat_router
from saxophone.retrieval.question_retrieval import (
    QuestionRequest,
    RetrievalBundle,
    RetrievalBundleStatus,
)
from saxophone.retrieval.renderers import AnswerContextModel, SourceParagraph


class _Gate:
    def __init__(self, *, rejected: tuple[str, ...] = ()) -> None:
        self.rejected = set(rejected)
        self.calls: list[tuple[str, ...]] = []

    async def validate(self, image_refs: tuple[str, ...]) -> tuple[str, ...]:
        self.calls.append(image_refs)
        if self.rejected.intersection(image_refs):
            raise ValueError("image artifact is unavailable")
        return image_refs


class _Retrieval:
    def __init__(self, bundle: RetrievalBundle) -> None:
        self.bundle = bundle

    async def retrieve(self, request: QuestionRequest) -> RetrievalBundle:
        return self.bundle


class _Provider:
    def __init__(self, used_refs: list[str]) -> None:
        self.used_refs = used_refs

    async def generate_structured(self, **kwargs):
        return kwargs["response_model"].model_validate(
            {"answer": "Supported answer [1].", "used_paragraph_refs": self.used_refs}
        )


def _paragraph(
    ref: str,
    *,
    image_refs: tuple[str, ...] = (),
    image_captions: dict[str, str] | None = None,
) -> SourceParagraph:
    return SourceParagraph(
        ref,
        "music-theory.md",
        "Triads",
        (),
        f"Text for {ref}.",
        (),
        ("12",),
        image_refs,
        f"chunk-{ref}",
        image_captions or {},
    )


def _bundle(paragraphs: tuple[SourceParagraph, ...]) -> RetrievalBundle:
    return RetrievalBundle(
        RetrievalBundleStatus.READY,
        "What is a triad?",
        (),
        "# Retrieval Context",
        AnswerContextModel((), paragraphs, tuple(p.paragraph_ref for p in paragraphs)),
    )


@pytest.mark.anyio
async def test_grounded_answer_validates_images_only_for_cited_paragraphs() -> None:
    cited = _paragraph(
        "paragraph-cited",
        image_refs=("images/cited.png",),
    )
    uncited = _paragraph("paragraph-uncited", image_refs=("images/uncited.png",))
    gate = _Gate()
    service = GroundedAnswerService(
        retrieval=_Retrieval(_bundle((cited, uncited))),
        provider=_Provider(["1"]),
        model_version="answer-v1",
        image_artifact_gate=gate,
    )

    result = await service.answer(QuestionRequest("What is a triad?"))

    assert result.status is GroundedAnswerStatus.ANSWERED
    assert result.sources[0].image_refs == ("images/cited.png",)
    assert gate.calls == [("images/cited.png",)]


@pytest.mark.anyio
async def test_grounded_answer_suppresses_unavailable_image_and_keeps_source() -> None:
    paragraph = _paragraph("paragraph-cited", image_refs=("images/missing.png",))
    service = GroundedAnswerService(
        retrieval=_Retrieval(_bundle((paragraph,))),
        provider=_Provider(["1"]),
        model_version="answer-v1",
        image_artifact_gate=_Gate(rejected=("images/missing.png",)),
    )

    result = await service.answer(QuestionRequest("What is a triad?"))

    assert result.sources[0].image_refs == ()
    assert result.sources[0].image_errors == ("image unavailable",)


@dataclass
class _LegacyAgentChat:
    result: object

    async def answer(self, request: QuestionRequest) -> object:
        return self.result


def _router(agent_chat: object, gate: object | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(
        build_agent_chat_router(agent_chat=agent_chat, image_artifact_gate=gate)
    )
    return app


def test_agent_chat_response_exposes_validated_image_metadata_per_citation() -> None:
    gate = _Gate()
    result = GroundedAnswerResponse(
        GroundedAnswerStatus.ANSWERED,
        "A supported answer.",
        (
            AnswerSource(
                "paragraph-cited",
                "chunk-cited",
                "music-theory.md",
                page_start=12,
                page_end=12,
                image_refs=("images/triad.png",),
                image_captions={"images/triad.png": "Triad diagram"},
            ),
            AnswerSource(
                "paragraph-without-image",
                "chunk-no-image",
                "music-theory.md",
                page_start=13,
                page_end=13,
            ),
        ),
        "answer-v1",
    )

    response = TestClient(_router(_LegacyAgentChat(result), gate)).post(
        "/agent/chat/messages", json={"question": "What is a triad?"}
    )

    assert response.status_code == 200
    sources = response.json()["sources"]
    assert sources[0]["images"] == [
        {
            "ref": "images/triad.png",
            "url": "/api/v1/assets/images/triad.png",
            "caption": "Triad diagram",
            "alt": "Hình minh họa được trích từ nguồn [1]",
        }
    ]
    assert "images" not in sources[1]
    assert gate.calls == [("images/triad.png",)]


def test_agent_chat_response_skips_unavailable_images_and_reports_source_error() -> None:
    result = GroundedAnswerResponse(
        GroundedAnswerStatus.ANSWERED,
        "A supported answer.",
        (
            AnswerSource(
                "paragraph-cited",
                "chunk-cited",
                "music-theory.md",
                image_refs=("images/missing.png",),
            ),
        ),
        "answer-v1",
    )

    response = TestClient(
        _router(_LegacyAgentChat(result), _Gate(rejected=("images/missing.png",)))
    ).post("/agent/chat/messages", json={"question": "What is a triad?"})

    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert "images" not in source
    assert source["image_errors"] == ["image unavailable"]


def test_agent_chat_response_rejects_unsafe_image_before_gate() -> None:
    result = GroundedAnswerResponse(
        GroundedAnswerStatus.ANSWERED,
        "A supported answer.",
        (
            AnswerSource(
                "paragraph-cited",
                "chunk-cited",
                "music-theory.md",
                image_refs=("../secret.png",),
            ),
        ),
        "answer-v1",
    )
    gate = _Gate()

    response = TestClient(_router(_LegacyAgentChat(result), gate)).post(
        "/agent/chat/messages", json={"question": "What is a triad?"}
    )

    source = response.json()["sources"][0]
    assert "images" not in source
    assert source["image_errors"] == ["image unavailable"]
    assert gate.calls == []


def test_agent_run_result_projects_only_synthesized_image_evidence() -> None:
    builder = EvidenceLedgerBuilder(
        "run-images", "What is a triad?", SelectionStrategy.PARAGRAPH_DIRECT
    )
    first = builder.add_document(
        source_ref="music-theory.md",
        chunk_id="chunk-1",
        paragraph_ref="paragraph-1",
        text="A major triad has three notes.",
        page=12,
        image_refs=("images/major.png",),
    )
    second = builder.add_document(
        source_ref="music-theory.md",
        chunk_id="chunk-2",
        paragraph_ref="paragraph-2",
        text="A minor triad lowers the third.",
        page=13,
    )
    ledger = builder.build()
    synthesis = SynthesisResult(
        "A supported answer.",
        used_evidence_ids=(first.evidence_id, second.evidence_id),
        citations=(Citation(first.evidence_id, "[1]"), Citation(second.evidence_id, "[2]")),
        image_evidence_ids=(first.evidence_id,),
    )
    result = AgentRunResult(
        run_id="run-images",
        outcome=AgentOutcome.ANSWERED,
        stage=AgentStage.COMPLETED,
        budget=RunBudget(),
        answer=synthesis.answer,
        ledger=ledger,
        synthesis=synthesis,
    )

    response = TestClient(_router(_LegacyAgentChat(result), _Gate())).post(
        "/agent/chat/messages", json={"question": "What is a triad?"}
    )

    assert response.status_code == 200
    sources = response.json()["sources"]
    assert sources[0]["images"][0]["ref"] == "images/major.png"
    assert "images" not in sources[1]


def test_agent_chat_asset_contract_is_present_in_frontend() -> None:
    app = _router(_LegacyAgentChat(GroundedAnswerResponse(
        GroundedAnswerStatus.NO_RETRIEVAL_CONTEXT,
        None,
        (),
    )))
    script = TestClient(app).get("/agent/chat/assets/chat.js")

    assert script.status_code == 200
    assert "source.images" in script.text
    assert "createElement(\"img\")" in script.text
    assert "image_errors" in script.text
