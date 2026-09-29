"""Compatibility adapter for pre-agent selector injections.

The active agent boundary receives typed selector adapters directly.  Older
retrieval callers may still provide provider-backed selectors, so this module
keeps that normalization behind an explicit compatibility seam.
"""

from __future__ import annotations

from typing import Any

from saxophone.agent.evidence_selection import (
    ConceptRoleSelector,
    ParagraphDirectSelector,
)

from .paragraph_selection import StructuredParagraphSelector


def adapt_legacy_selector(selector: Any) -> ParagraphDirectSelector | ConceptRoleSelector:
    """Wrap a pre-agent selector without branching in active retrieval code."""

    if selector is None:
        raise TypeError("selector is required")
    if isinstance(selector, (ParagraphDirectSelector, ConceptRoleSelector)):
        return selector
    if isinstance(selector, StructuredParagraphSelector):
        return ParagraphDirectSelector(selector)
    return ConceptRoleSelector(selector)


__all__ = ["adapt_legacy_selector"]
