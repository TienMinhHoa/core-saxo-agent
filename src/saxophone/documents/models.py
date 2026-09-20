"""Immutable references to versioned artifacts owned by the backend."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from saxophone.documents.policies import is_safe_artifact_reference


class ArtifactKind(StrEnum):
    """Artifact categories shared by extraction and ingestion workflows."""

    SOURCE_PDF = "source_pdf"
    MARKDOWN = "markdown"
    LAYOUT = "layout"
    IMAGE = "image"
    EXTRACTION_MANIFEST = "extraction_manifest"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Stable metadata for an immutable artifact.

    The contract intentionally carries no local filesystem path.  Storage
    adapters can map this identity to a safe path or remote transfer handle
    without leaking storage details into application code.
    """

    artifact_id: str
    version: str
    kind: ArtifactKind
    media_type: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        _require_non_blank("artifact_id", self.artifact_id)
        if not is_safe_artifact_reference(self.artifact_id):
            raise ValueError("artifact_id must be a safe relative reference")
        _require_non_blank("version", self.version)
        if not is_safe_artifact_reference(self.version):
            raise ValueError("version must be a safe relative reference")
        if not isinstance(self.kind, ArtifactKind):
            raise ValueError("kind must be an ArtifactKind")
        _require_non_blank("media_type", self.media_type)
        if not isinstance(self.sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.sha256
        ):
            raise ValueError("sha256 must be a lowercase 64-character hexadecimal digest")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int):
            raise ValueError("size_bytes must be an integer")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")


def _require_non_blank(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
