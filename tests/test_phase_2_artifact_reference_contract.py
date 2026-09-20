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
        ("kind", "extraction_manifest"),
        ("media_type", 123),
        ("media_type", ""),
        ("sha256", "not-a-sha256"),
        ("size_bytes", True),
        ("size_bytes", 1.5),
    ],
)
def test_artifact_reference_rejects_invalid_identity_fields(field: str, value: object) -> None:
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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_id", "../outside"),
        ("artifact_id", "document/../outside"),
        ("artifact_id", r"document\outside"),
        ("artifact_id", "/absolute"),
        ("artifact_id", "C:/outside"),
        ("artifact_id", "document//file"),
        ("artifact_id", "document/./file"),
        ("version", "../outside"),
        ("version", r"extract\v1"),
        ("version", "/absolute"),
        ("version", "C:/outside"),
        ("version", "extract//v1"),
        ("version", "extract/./v1"),
    ],
)
def test_artifact_reference_rejects_path_escaping_or_noncanonical_identity(
    field: str, value: str
) -> None:
    fields = {
        "artifact_id": "document-123/manifest",
        "version": "extract-v1",
        "kind": ArtifactKind.EXTRACTION_MANIFEST,
        "media_type": "application/json",
        "sha256": "a" * 64,
        "size_bytes": 128,
    }
    fields[field] = value

    with pytest.raises(ValueError, match=field):
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
