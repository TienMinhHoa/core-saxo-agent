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
from .ports import (
    TagCatalogRepository,
    TagConflictResolver,
    TagGenerator,
    TaggedParagraphRepository,
)


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
        if generated.tagging_profile != tagging_profile:
            raise ValueError("generated result tagging profile does not match request")
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
        if resolution.resolution_profile != resolution_profile:
            raise ValueError("resolution profile does not match request")
        if resolution.generated_tags != generated.tags:
            raise ValueError("resolution generated tags do not match generation result")
        if tuple(item.generated_tag for item in resolution.resolutions) != generated.tags:
            raise ValueError("resolution order does not match generation result")
        return TaggedParagraph(
            paragraph_id=paragraph.paragraph_id,
            text=paragraph.text,
            generated_tags=generated.tags,
            tags=tuple(item.resolved_tag for item in resolution.resolutions),
            status="completed",
        )


class TagAndPersistParagraph:
    """Run tagging and publish its two durable projections."""

    def __init__(
        self,
        tag_paragraph: TagParagraph,
        paragraph_repository: TaggedParagraphRepository,
        catalog_repository: TagCatalogRepository,
    ) -> None:
        self._tag_paragraph = tag_paragraph
        self._paragraph_repository = paragraph_repository
        self._catalog_repository = catalog_repository

    async def execute(
        self,
        paragraph: ParagraphBlock,
        *,
        tagging_profile: str,
        resolution_profile: str,
    ) -> TaggedParagraph:
        existing_tags = tuple(
            ExistingTagCandidate(tag) for tag in await self._catalog_repository.list()
        )
        tagged = await self._tag_paragraph.execute(
            paragraph,
            tagging_profile=tagging_profile,
            resolution_profile=resolution_profile,
            existing_tags=existing_tags,
        )
        await self._paragraph_repository.upsert(tagged)
        await self._catalog_repository.add(tagged.tags)
        return tagged
