"""Validated DTOs at the retrieval-to-chat boundary."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class ChatStatus(StrEnum):
    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True, slots=True)
class GeneratedAnswer:
    """Provider output after the adapter has removed private reasoning."""

    answer: str
    model_version: str
    token_usage: Mapping[str, int]
    cost: float = 0.0

    def __post_init__(self) -> None:
        _require_text("answer", self.answer)
        _require_text("model_version", self.model_version)
        _validate_token_usage(self.token_usage)
        if not math.isfinite(self.cost) or self.cost < 0:
            raise ValueError("cost must be finite and non-negative")
        object.__setattr__(self, "token_usage", MappingProxyType(dict(self.token_usage)))


@dataclass(frozen=True, slots=True)
class ChatResult:
    """Safe chat response: answer and citations, never chain-of-thought."""

    status: ChatStatus
    answer: str | None
    citations: tuple[str, ...]
    evidence_bundle_ref: str | None
    model_version: str | None
    token_usage: Mapping[str, int]
    cost: float
    insufficiency_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ChatStatus):
            raise ValueError("status must be a ChatStatus")
        if not isinstance(self.citations, tuple):
            raise ValueError("citations must be a tuple")
        if self.status is ChatStatus.ANSWERED:
            _require_text("answer", self.answer)
            _require_text("evidence_bundle_ref", self.evidence_bundle_ref)
            _require_text("model_version", self.model_version)
            if not self.citations:
                raise ValueError("answered result must contain citations")
        elif (
            self.answer is not None
            or self.evidence_bundle_ref is not None
            or self.model_version is not None
            or self.citations
        ):
            raise ValueError(
                "insufficient result must not contain answer, evidence, model metadata, or citations"
            )
        if self.status is ChatStatus.INSUFFICIENT_EVIDENCE:
            _require_text("insufficiency_reason", self.insufficiency_reason)
        elif self.insufficiency_reason is not None:
            raise ValueError("answered result must not contain insufficiency reason")
        if any(not isinstance(ref, str) or not ref.strip() for ref in self.citations):
            raise ValueError("citations must contain non-blank refs")
        if len(set(self.citations)) != len(self.citations):
            raise ValueError("citations must be unique")
        _validate_token_usage(self.token_usage)
        if not math.isfinite(self.cost) or self.cost < 0:
            raise ValueError("cost must be finite and non-negative")
        object.__setattr__(self, "token_usage", MappingProxyType(dict(self.token_usage)))


def evidence_reference(retrieval_version: str, selected_refs: tuple[str, ...]) -> str:
    digest = hashlib.sha256("\n".join(selected_refs).encode("utf-8")).hexdigest()[:16]
    return f"evidence://{retrieval_version}/{digest}"


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")


def _validate_token_usage(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("token_usage must be a mapping")
    if any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        for key, count in value.items()
    ):
        raise ValueError("token_usage must contain non-negative integer values")
