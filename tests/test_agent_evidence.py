from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from saxophone.agent.contracts import Citation, EvidenceSourceType, SelectionStrategy
from saxophone.agent.evidence import (
    EvidenceLedger,
    EvidenceLedgerBuilder,
    stable_evidence_id,
)


def test_stable_evidence_id_is_deterministic_for_source_identity() -> None:
    first = stable_evidence_id(
        EvidenceSourceType.DOCUMENT,
        source_ref="music-theory.md",
        chunk="chunk-12",
        paragraph="paragraph-12-2",
    )
    second = stable_evidence_id(
        "document",
        source_ref="music-theory.md",
        chunk_id="chunk-12",
        paragraph_ref="paragraph-12-2",
    )

    assert first == second
    assert first.startswith("document:")
    assert first != stable_evidence_id(
        "document",
        source_ref="music-theory.md",
        chunk="chunk-12",
        paragraph="paragraph-12-3",
    )
    assert stable_evidence_id("web", url="https://example.test/source") == stable_evidence_id(
        "web",
        source_ref="A revised title",
        url="https://example.test/source",
    )


def test_ledger_builder_keeps_trace_and_freezes_the_built_snapshot() -> None:
    builder = EvidenceLedgerBuilder(
        run_id="run-1",
        question="What is a major triad?",
        selected_strategy=SelectionStrategy.PARAGRAPH_DIRECT,
    )
    evidence = builder.add_document(
        source_ref="music-theory.md",
        chunk_id="chunk-12",
        paragraph_ref="paragraph-12-2",
        text="A major triad has a root, third, and fifth.",
        page=12,
        image_refs=("images/triad.png",),
    )
    builder.add_search_trace("document_search", hit_count=1)
    ledger = builder.build(
        citations=(Citation(evidence.evidence_id, "[1]"),),
        image_evidence_ids=(evidence.evidence_id,),
    )

    builder.add_document(
        source_ref="music-theory.md",
        chunk_id="chunk-13",
        paragraph_ref="paragraph-13-1",
        text="A minor triad lowers the third.",
        page=13,
    )

    assert isinstance(ledger, EvidenceLedger)
    assert len(ledger.evidence) == 1
    assert ledger.used_evidence_ids == (evidence.evidence_id,)
    assert ledger.search_trace[0].tool == "document_search"
    assert ledger.evidence_by_id[evidence.evidence_id] is evidence
    with pytest.raises(FrozenInstanceError):
        ledger.evidence = ()  # type: ignore[misc]
    with pytest.raises(TypeError):
        ledger.evidence_by_id[evidence.evidence_id] = evidence  # type: ignore[index]


def test_ledger_builder_rejects_duplicate_identity_before_building() -> None:
    builder = EvidenceLedgerBuilder(
        run_id="run-1",
        question="What is a major triad?",
        selected_strategy="paragraph_direct",
    )
    kwargs = {
        "source_ref": "music-theory.md",
        "chunk_id": "chunk-12",
        "paragraph_ref": "paragraph-12-2",
        "text": "A major triad has a root, third, and fifth.",
        "page": 12,
    }
    builder.add_document(**kwargs)

    with pytest.raises(ValueError, match="unique"):
        builder.add_document(**kwargs)


def test_ledger_builder_normalizes_web_evidence_with_retrieval_metadata() -> None:
    builder = EvidenceLedgerBuilder(
        run_id="run-web",
        question="What is a tuning fork?",
        selected_strategy="paragraph_direct",
    )
    evidence = builder.add_web(
        title="Tuning fork",
        url="https://example.test/tuning-fork",
        snippet="A tuning fork produces a reference pitch.",
        retrieved_at="2026-09-29T00:00:00Z",
    )
    ledger = builder.build()

    assert evidence.source_type is EvidenceSourceType.WEB
    assert evidence.url == "https://example.test/tuning-fork"
    assert evidence.retrieved_at == "2026-09-29T00:00:00Z"
    assert ledger.evidence == (evidence,)
    assert ledger.used_evidence_ids == (evidence.evidence_id,)
