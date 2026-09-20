"""Pure policies for document-owned references."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


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

    if not isinstance(media_type, str):
        return False
    main_type = media_type.split(";", 1)[0].strip().lower()
    return main_type.startswith("image/") and len(main_type) > len("image/")
