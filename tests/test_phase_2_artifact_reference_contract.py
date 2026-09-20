from __future__ import annotations

import pytest

from saxophone.documents.models import ArtifactKind, ArtifactRef


def test_artifact_reference_is_immutable_and_keeps_versioned_identity() -> None:
    artifact = ArtifactRef(
        artifact_id="document-123/manifest",
        version="extract-v1",
        kind=ArtifactKind.EXTRACTION_MANIFEST,
        media_type="application/json",
        sha256="a" * 64,
        size_bytes=128,
    )

    assert artifact.artifact_id == "document-123/manifest"
    assert artifact.version == "extract-v1"
    assert artifact.kind is ArtifactKind.EXTRACTION_MANIFEST
    assert artifact.media_type == "application/json"
    assert artifact.sha256 == "a" * 64
    assert artifact.size_bytes == 128
    with pytest.raises(AttributeError):
        artifact.version = "extract-v2"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_id", ""),
        ("version", "  "),
        ("media_type", ""),
        ("sha256", "not-a-sha256"),
    ],
)
def test_artifact_reference_rejects_invalid_identity_fields(field: str, value: str) -> None:
    fields = {
        "artifact_id": "document-123/manifest",
        "version": "extract-v1",
        "kind": ArtifactKind.EXTRACTION_MANIFEST,
        "media_type": "application/json",
        "sha256": "a" * 64,
        "size_bytes": 128,
    }
    fields[field] = value

    with pytest.raises(ValueError, match=field if field != "sha256" else "sha256"):
        ArtifactRef(**fields)


@pytest.mark.parametrize("size_bytes", [-1, -100])
def test_artifact_reference_rejects_negative_size(size_bytes: int) -> None:
    with pytest.raises(ValueError, match="size_bytes"):
        ArtifactRef(
            artifact_id="document-123/manifest",
            version="extract-v1",
            kind=ArtifactKind.EXTRACTION_MANIFEST,
            media_type="application/json",
            sha256="a" * 64,
            size_bytes=size_bytes,
        )
