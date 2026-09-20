from __future__ import annotations

import pytest

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.documents.policies import is_image_media_type


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
        ("media_type", "application"),
        ("media_type", "application/json/xml"),
        ("media_type", " application/json"),
        ("media_type", "application/js(on)"),
        ("media_type", "application/json,xml"),
        ("media_type", "application/jäson"),
        ("media_type", "application /json"),
        ("media_type", "application/json;\tcharset=utf-8"),
        ("media_type", "application/json;\ncharset=utf-8"),
        ("media_type", "application/json; charset=utf-8\x7f"),
        ("media_type", "application/json;"),
        ("media_type", "application/json; charset"),
        ("media_type", "application/json; =utf-8"),
        ("media_type", "application/json; charset="),
        ("media_type", "application/json; charset=utf-8; ;"),
        ("media_type", 'application/json; charset="utf"8"'),
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
        ("artifact_id", "document/manifest\nnext"),
        ("artifact_id", "document/manifest\tdebug"),
        ("artifact_id", "document/manifest\x7fdebug"),
        ("artifact_id", "/absolute"),
        ("artifact_id", "C:/outside"),
        ("artifact_id", "document//file"),
        ("artifact_id", "document/./file"),
        ("version", "../outside"),
        ("version", r"extract\v1"),
        ("version", "extract-v1\nnext"),
        ("version", "extract-v1\tdebug"),
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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_id", "document/report."),
        ("artifact_id", "document/report "),
        ("artifact_id", "document/report?.json"),
        ("artifact_id", "document/CON/report"),
        ("artifact_id", "document/archive/COM1.txt"),
        ("version", "extract-v1."),
        ("version", "extract-v1 "),
        ("version", "extract?stable"),
        ("version", "LPT1"),
    ],
)
def test_artifact_reference_rejects_windows_unsafe_storage_components(
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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_id", "document/cafe\u0301/manifest"),
        ("version", "extract-cafe\u0301-v1"),
    ],
)
def test_artifact_reference_rejects_non_nfc_identity(
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


def test_artifact_reference_accepts_nfc_unicode_identity() -> None:
    artifact = ArtifactRef(
        artifact_id="document/caf\u00e9/manifest",
        version="extract-v1",
        kind=ArtifactKind.EXTRACTION_MANIFEST,
        media_type="application/json",
        sha256="a" * 64,
        size_bytes=128,
    )

    assert artifact.artifact_id == "document/caf\u00e9/manifest"


@pytest.mark.parametrize(
    "document_ref",
    [
        "document\nnext",
        "document\tdebug",
        "document\x7fdebug",
        "document/cafe\u0301",
    ],
)
def test_document_reference_policy_rejects_control_characters_and_non_nfc(
    document_ref: str,
) -> None:
    from saxophone.documents.policies import is_safe_document_reference

    assert is_safe_document_reference(document_ref) is False


def test_document_reference_policy_accepts_nfc_unicode_identity() -> None:
    from saxophone.documents.policies import is_safe_document_reference

    assert is_safe_document_reference("document-caf\u00e9") is True


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


@pytest.mark.parametrize("sha256", [None, 123, b"0" * 64, True])
def test_artifact_reference_rejects_non_string_sha256_without_type_error(
    sha256: object,
) -> None:
    with pytest.raises(ValueError, match="sha256"):
        ArtifactRef(
            artifact_id="document-123/manifest",
            version="extract-v1",
            kind=ArtifactKind.EXTRACTION_MANIFEST,
            media_type="application/json",
            sha256=sha256,  # type: ignore[arg-type]
            size_bytes=128,
        )


def test_artifact_reference_accepts_mime_parameters() -> None:
    artifact = ArtifactRef(
        artifact_id="document-123/manifest",
        version="extract-v1",
        kind=ArtifactKind.EXTRACTION_MANIFEST,
        media_type="application/json; charset=utf-8",
        sha256="a" * 64,
        size_bytes=128,
    )

    assert artifact.media_type == "application/json; charset=utf-8"


def test_artifact_reference_accepts_quoted_mime_parameter_value() -> None:
    artifact = ArtifactRef(
        artifact_id="document-123/manifest",
        version="extract-v1",
        kind=ArtifactKind.EXTRACTION_MANIFEST,
        media_type='application/json; charset="utf-8"',
        sha256="a" * 64,
        size_bytes=128,
    )

    assert artifact.media_type == 'application/json; charset="utf-8"'


def test_artifact_reference_accepts_semicolon_inside_quoted_mime_parameter() -> None:
    artifact = ArtifactRef(
        artifact_id="document-123/manifest",
        version="extract-v1",
        kind=ArtifactKind.EXTRACTION_MANIFEST,
        media_type='application/json; profile="urn:example;a"',
        sha256="a" * 64,
        size_bytes=128,
    )

    assert artifact.media_type == 'application/json; profile="urn:example;a"'


@pytest.mark.parametrize(
    "media_type",
    [
        'application/json; profile="urn:example;a',
        'application/json; profile="urn:example;a"; charset=utf-8"',
    ],
)
def test_artifact_reference_rejects_malformed_quoted_mime_parameters(
    media_type: str,
) -> None:
    with pytest.raises(ValueError, match="media_type"):
        ArtifactRef(
            artifact_id="document-123/manifest",
            version="extract-v1",
            kind=ArtifactKind.EXTRACTION_MANIFEST,
            media_type=media_type,
            sha256="a" * 64,
            size_bytes=128,
        )


def test_artifact_reference_accepts_standard_mime_token_punctuation() -> None:
    artifact = ArtifactRef(
        artifact_id="document-123/manifest",
        version="extract-v1",
        kind=ArtifactKind.EXTRACTION_MANIFEST,
        media_type="application/vnd.example+json",
        sha256="a" * 64,
        size_bytes=128,
    )

    assert artifact.media_type == "application/vnd.example+json"


def test_image_media_type_requires_a_valid_mime_parameter_list() -> None:
    assert is_image_media_type('image/svg+xml; profile="urn:example;a"') is True


@pytest.mark.parametrize(
    "media_type",
    [
        "image/png;",
        'image/png; profile="unterminated',
        "image/png garbage",
    ],
)
def test_image_media_type_rejects_malformed_mime_values(media_type: str) -> None:
    assert is_image_media_type(media_type) is False
