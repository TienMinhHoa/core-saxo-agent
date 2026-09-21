"""Stable public facade for document-owned contracts and policies."""

from importlib import import_module
from typing import Any


_EXPORTS = {
    "ArtifactKind": ("saxophone.documents.models", "ArtifactKind"),
    "ArtifactRef": ("saxophone.documents.models", "ArtifactRef"),
    "ArtifactRepository": ("saxophone.documents.ports", "ArtifactRepository"),
    "ImageArtifactResolver": ("saxophone.documents.ports", "ImageArtifactResolver"),
    "KnowledgeChunk": ("saxophone.documents.knowledge", "KnowledgeChunk"),
    "KnowledgeRepository": ("saxophone.documents.ports", "KnowledgeRepository"),
    "is_image_media_type": ("saxophone.documents.policies", "is_image_media_type"),
    "is_safe_artifact_reference": (
        "saxophone.documents.policies",
        "is_safe_artifact_reference",
    ),
    "is_safe_document_reference": (
        "saxophone.documents.policies",
        "is_safe_document_reference",
    ),
    "is_safe_media_type": ("saxophone.documents.policies", "is_safe_media_type"),
    "is_safe_relative_image_reference": (
        "saxophone.documents.policies",
        "is_safe_relative_image_reference",
    ),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(name) from error
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
