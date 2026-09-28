"""Evidence ledger construction and identity helpers.

The immutable DTOs remain defined in :mod:`saxophone.agent.contracts` so the
existing public contract stays compatible.  This module owns the application
boundary that collects normalized search output into a detached ledger before
it is handed to synthesis.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable

from .contracts import (
    AgentQuestion,
    Citation,
    EvidenceItem,
    EvidenceLedger,
    EvidenceSourceType,
    SearchTrace,
    SelectionStrategy,
)


def stable_evidence_id(
    source_type: EvidenceSourceType | str,
    *,
    source_ref: str | None = None,
    chunk: str | None = None,
    paragraph: str | None = None,
    url: str | None = None,
    chunk_id: str | None = None,
    paragraph_ref: str | None = None,
) -> str:
    """Return a deterministic id for one source location.

    IDs are derived only from source identity, never from mutable answer text,
    so retries and repeated runs can refer to the same selected fragment
    consistently.  The digest keeps URLs and file paths out of user-visible
    labels while retaining a readable source-type prefix.
    """

    try:
        normalized_source = (
            source_type.value
            if isinstance(source_type, EvidenceSourceType)
            else EvidenceSourceType(source_type).value
        )
    except (TypeError, ValueError) as error:
        raise ValueError("source_type must be document or web") from error

    chunk = _coalesce_alias("chunk", chunk, "chunk_id", chunk_id)
    paragraph = _coalesce_alias("paragraph", paragraph, "paragraph_ref", paragraph_ref)
    normalized_source_ref = _normalize_identity_part(source_ref)
    normalized_chunk = _normalize_identity_part(chunk)
    normalized_paragraph = _normalize_identity_part(paragraph)
    normalized_url = _normalize_identity_part(url)
    if normalized_source == EvidenceSourceType.WEB.value:
        # URLs are the stable identity for web evidence; titles can change.
        normalized_source_ref = ""
    parts = (normalized_source_ref, normalized_chunk, normalized_paragraph, normalized_url)
    if not any(parts):
        raise ValueError("at least one source identity field is required")
    payload = "\x1f".join((normalized_source, *parts)).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:20]
    return f"{normalized_source}:{digest}"


@dataclass(slots=True)
class EvidenceLedgerBuilder:
    """Collect evidence and produce a detached immutable ledger snapshot."""

    run_id: str
    question: str | AgentQuestion
    selected_strategy: SelectionStrategy
    _evidence: list[EvidenceItem] = field(default_factory=list, init=False)
    _search_trace: list[SearchTrace] = field(default_factory=list, init=False)
    _normalized_queries: list[str] = field(default_factory=list, init=False)

    @property
    def evidence(self) -> tuple[EvidenceItem, ...]:
        """Expose a snapshot without leaking the mutable builder list."""

        return tuple(self._evidence)

    @property
    def search_trace(self) -> tuple[SearchTrace, ...]:
        """Return the trace collected so far as an immutable tuple."""

        return tuple(self._search_trace)

    def add(self, evidence: EvidenceItem) -> EvidenceItem:
        """Add one evidence item, rejecting duplicate stable identities."""

        if not isinstance(evidence, EvidenceItem):
            raise TypeError("evidence must be an EvidenceItem")
        if any(item.evidence_id == evidence.evidence_id for item in self._evidence):
            raise ValueError("evidence IDs must be unique")
        self._evidence.append(evidence)
        return evidence

    def add_document(
        self,
        *,
        source_ref: str,
        chunk_id: str,
        paragraph_ref: str,
        text: str,
        page: int,
        image_refs: Iterable[str] = (),
        evidence_id: str | None = None,
    ) -> EvidenceItem:
        """Normalize a document paragraph into an evidence item."""

        item = EvidenceItem(
            evidence_id=evidence_id
            or stable_evidence_id(
                EvidenceSourceType.DOCUMENT,
                source_ref=source_ref,
                chunk=chunk_id,
                paragraph=paragraph_ref,
            ),
            source_type=EvidenceSourceType.DOCUMENT,
            source_ref=source_ref,
            chunk=chunk_id,
            paragraph=paragraph_ref,
            text=text,
            page=page,
            image_refs=tuple(image_refs),
        )
        return self.add(item)

    def add_web(
        self,
        *,
        title: str,
        url: str,
        snippet: str,
        retrieved_at: str,
        content: str = "",
        evidence_id: str | None = None,
    ) -> EvidenceItem:
        """Normalize one web result with the URL and retrieval timestamp."""

        text = content.strip() or snippet
        item = EvidenceItem(
            evidence_id=evidence_id
            or stable_evidence_id(EvidenceSourceType.WEB, url=url),
            source_type=EvidenceSourceType.WEB,
            source_ref=title,
            text=text,
            url=url,
            retrieved_at=retrieved_at,
        )
        return self.add(item)

    def add_search_trace(
        self,
        trace: SearchTrace | str,
        *,
        query_count: int = 1,
        hit_count: int = 0,
        status: str = "completed",
    ) -> SearchTrace:
        """Record a safe tool summary without retaining prompt contents."""

        normalized = (
            trace
            if isinstance(trace, SearchTrace)
            else SearchTrace(trace, query_count, hit_count, status)
        )
        self._search_trace.append(normalized)
        return normalized

    def add_query(self, query: str) -> str:
        """Remember a normalized query used by the search phase."""

        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be blank")
        normalized = query.strip()
        if normalized not in self._normalized_queries:
            self._normalized_queries.append(normalized)
        return normalized

    def build(
        self,
        *,
        used_evidence_ids: Iterable[str] | None = None,
        citations: Iterable[Citation] = (),
        image_evidence_ids: Iterable[str] = (),
    ) -> EvidenceLedger:
        """Freeze all collected values into a validated ledger snapshot."""

        question = (
            self.question.question
            if isinstance(self.question, AgentQuestion)
            else self.question
        )
        if not self._normalized_queries and isinstance(question, str) and question.strip():
            normalized_queries = (question.strip(),)
        else:
            normalized_queries = tuple(self._normalized_queries)
        selected_ids = (
            tuple(item.evidence_id for item in self._evidence)
            if used_evidence_ids is None
            else tuple(used_evidence_ids)
        )
        return EvidenceLedger(
            run_id=self.run_id,
            question=question,
            selected_strategy=self.selected_strategy,
            evidence=tuple(self._evidence),
            search_trace=tuple(self._search_trace),
            normalized_queries=normalized_queries,
            used_evidence_ids=selected_ids,
            citations=tuple(citations),
            image_evidence_ids=tuple(image_evidence_ids),
        )


def _normalize_identity_part(value: str | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("source identity fields must be strings")
    return value.strip()


def _coalesce_alias(
    primary_name: str,
    primary: str | None,
    alias_name: str,
    alias: str | None,
) -> str | None:
    if primary is not None and alias is not None and primary != alias:
        raise ValueError(f"{primary_name} and {alias_name} must match when both are provided")
    return primary if primary is not None else alias


__all__ = [
    "Citation",
    "EvidenceItem",
    "EvidenceLedger",
    "EvidenceLedgerBuilder",
    "EvidenceSourceType",
    "SearchTrace",
    "SelectionStrategy",
    "stable_evidence_id",
]
