"""Pure policies for document-owned references."""

from __future__ import annotations

import unicodedata
from pathlib import Path
from urllib.parse import urlparse


_MIME_TOKEN_CHARACTERS = frozenset(
    "!#$%&'*+-.^_`|~"
)


def is_safe_artifact_reference(artifact_id: object) -> bool:
    """Return whether an artifact identity is safe for backend-owned storage."""

    if not isinstance(artifact_id, str) or not artifact_id or artifact_id != artifact_id.strip():
        return False
    if unicodedata.normalize("NFC", artifact_id) != artifact_id:
        return False
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in artifact_id):
        return False
    if any(character in artifact_id for character in ("\\", "\x00", ":")):
        return False
    parts = artifact_id.split("/")
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts)


def is_safe_document_reference(document_ref: object) -> bool:
    """Return whether a document identity can be used as one path component."""

    if not isinstance(document_ref, str) or not document_ref.strip():
        return False
    if document_ref != document_ref.strip():
        return False
    if unicodedata.normalize("NFC", document_ref) != document_ref:
        return False
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in document_ref):
        return False
    if any(character in document_ref for character in ("/", "\\", "\x00", ":")):
        return False
    parsed = urlparse(document_ref)
    return not parsed.scheme and not parsed.netloc and document_ref not in {".", ".."}


def is_safe_relative_image_reference(image_ref: object) -> bool:
    """Return whether an image reference has one safe relative spelling."""

    if not isinstance(image_ref, str) or not image_ref.strip():
        return False
    candidate = image_ref.strip().replace("\\", "/")
    if candidate != image_ref:
        return False
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc or candidate.startswith("/"):
        return False
    path = Path(candidate)
    return ".." not in path.parts and path.as_posix() == candidate


def is_image_media_type(media_type: object) -> bool:
    """Return whether a media type is an image MIME type."""

    if not is_safe_media_type(media_type):
        return False
    assert isinstance(media_type, str)
    main_type = media_type.split(";", 1)[0].strip().lower()
    return main_type.startswith("image/") and len(main_type) > len("image/")


def is_safe_media_type(media_type: object) -> bool:
    """Return whether a media type has a safe type/subtype structure."""

    if not isinstance(media_type, str) or not media_type or media_type != media_type.strip():
        return False
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in media_type):
        return False
    components = _split_mime_components(media_type)
    if components is None:
        return False
    main_type, *parameters = components
    if any(not _is_mime_parameter(parameter) for parameter in parameters):
        return False
    main_type = main_type.strip()
    parts = main_type.split("/")
    if len(parts) != 2 or not all(parts):
        return False
    return all(_is_mime_token(part) for part in parts)


def _is_mime_token(value: str) -> bool:
    return bool(value) and all(
        character.isascii()
        and (character.isalnum() or character in _MIME_TOKEN_CHARACTERS)
        for character in value
    )


def _is_mime_parameter(value: str) -> bool:
    """Return whether a MIME parameter has a name and token/quoted value."""

    name, separator, parameter_value = value.strip().partition("=")
    if not separator or not _is_mime_token(name.strip()):
        return False
    parameter_value = parameter_value.strip()
    if _is_mime_token(parameter_value):
        return True
    if not (
        len(parameter_value) >= 2
        and parameter_value.startswith('"')
        and parameter_value.endswith('"')
    ):
        return False
    escaped = False
    for character in parameter_value[1:-1]:
        if character in {'\r', '\n', '\x00', '\x7f'}:
            return False
        if character == '"' and not escaped:
            return False
        escaped = character == "\\" and not escaped
        if character != "\\":
            escaped = False
    return not escaped


def _split_mime_components(media_type: str) -> list[str] | None:
    """Split MIME components without treating quoted semicolons as separators."""

    components: list[str] = []
    start = 0
    in_quotes = False
    escaped = False
    for index, character in enumerate(media_type):
        if in_quotes:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_quotes = False
            continue
        if character == '"':
            in_quotes = True
        elif character == ";":
            components.append(media_type[start:index])
            start = index + 1
    if in_quotes or escaped:
        return None
    components.append(media_type[start:])
    return components
