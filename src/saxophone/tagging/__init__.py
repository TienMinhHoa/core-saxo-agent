"""Provider-independent paragraph tagging contracts."""

from .models import ParagraphBlock, TagGenerationRequest, TagGenerationResult, TaggedParagraph
from .ports import TagGenerator

__all__ = [
    "ParagraphBlock",
    "TagGenerationRequest",
    "TagGenerationResult",
    "TaggedParagraph",
    "TagGenerator",
]
