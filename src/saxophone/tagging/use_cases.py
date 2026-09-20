"""Application orchestration for paragraph tagging."""

from __future__ import annotations

from collections.abc import Sequence

from .models import (
    ExistingTagCandidate,
    ParagraphBlock,
    TagConflictResolutionRequest,
    TagGenerationRequest,
    TaggedParagraph,
)
from .ports import TagConflictResolver, TagGenerator


class TagParagraph:
    """Generate tags, resolve conflicts, and return a validated projection."""

    def __init__(self, generator: TagGenerator, resolver: TagConflictResolver) -> None:
        self._generator = generator
        self._resolver = resolver

    async def execute(
        self,
        paragraph: ParagraphBlock,
        *,
        tagging_profile: str,
        resolution_profile: str,
        existing_tags: Sequence[ExistingTagCandidate] = (),
    ) -> TaggedParagraph:
        generated = await self._generator.generate(
            TagGenerationRequest(paragraph=paragraph, tagging_profile=tagging_profile)
        )
        if generated.paragraph_id != paragraph.paragraph_id:
            raise ValueError("generated result paragraph ID does not match paragraph")
        resolution = await self._resolver.resolve(
            TagConflictResolutionRequest(
                paragraph_id=paragraph.paragraph_id,
                generated_tags=generated.tags,
                existing_tags=tuple(existing_tags),
                resolution_profile=resolution_profile,
            )
        )
        if resolution.paragraph_id != paragraph.paragraph_id:
            raise ValueError("resolution paragraph ID does not match paragraph")
        if resolution.generated_tags and resolution.generated_tags != generated.tags:
            raise ValueError("resolution generated tags do not match generation result")
        return TaggedParagraph(
            paragraph_id=paragraph.paragraph_id,
            text=paragraph.text,
            generated_tags=generated.tags,
            tags=tuple(item.resolved_tag for item in resolution.resolutions),
            status="completed",
        )
