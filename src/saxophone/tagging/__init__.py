"""Provider-independent paragraph tagging contracts."""

from .models import ParagraphBlock, TagGenerationRequest, TagGenerationResult
from .ports import TagGenerator

__all__ = [
    "ParagraphBlock",
    "TagGenerationRequest",
    "TagGenerationResult",
    "TagGenerator",
]
