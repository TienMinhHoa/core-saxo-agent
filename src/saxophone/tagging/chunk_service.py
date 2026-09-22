"""Application service for one validated concept-role tagging call per chunk."""

from __future__ import annotations

from dataclasses import dataclass

from .chunk_models import ChunkTaggingRequest, ChunkTaggingResult
from .models import ParagraphConceptRole
from .ports import ChunkTagger


@dataclass(frozen=True, slots=True)
class ChunkTaggingRun:
    """A validated provider result and its relational source-of-truth projection."""

    result: ChunkTaggingResult
    relations: tuple[ParagraphConceptRole, ...]


class ChunkTaggingService:
    """Run exactly one tagger call and project validated paragraph-concept roles."""

    def __init__(self, tagger: ChunkTagger) -> None:
        if not callable(getattr(tagger, "tag", None)):
            raise TypeError("tagger must provide tag")
        self._tagger = tagger

    async def tag_chunk(self, request: ChunkTaggingRequest) -> ChunkTaggingRun:
        if not isinstance(request, ChunkTaggingRequest):
            raise TypeError("request must be a ChunkTaggingRequest")
        result = await self._tagger.tag(request)
        if not isinstance(result, ChunkTaggingResult):
            raise TypeError("tagger must return ChunkTaggingResult")
        result.validate_against(request)
        relations = tuple(
            ParagraphConceptRole(paragraph.paragraph_ref, label.resolved_concept, role)
            for paragraph in result.paragraphs
            for label in paragraph.labels
            for role in label.roles
        )
        return ChunkTaggingRun(result=result, relations=relations)
