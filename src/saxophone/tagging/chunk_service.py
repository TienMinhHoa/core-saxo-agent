"""Application service for one validated concept-role tagging call per chunk."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .chunk_models import ChunkTaggingRequest, ChunkTaggingResult
from .models import ParagraphConceptRole
from .ports import ChunkTagger


@dataclass(frozen=True, slots=True)
class ChunkTaggingRun:
    """A validated provider result and its relational source-of-truth projection."""

    result: ChunkTaggingResult
    relations: tuple[ParagraphConceptRole, ...]


class _ChunkRelationRepository(Protocol):
    async def replace_chunk_relations(
        self,
        document_ref: str,
        source_version: str,
        paragraph_ids: tuple[str, ...],
        relations: tuple[ParagraphConceptRole, ...],
    ) -> None: ...


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


class ChunkTaggingPersistenceService:
    """Commit one validated chunk tagging run without replacing sibling chunks."""

    def __init__(
        self,
        tagging_service: ChunkTaggingService,
        repository: _ChunkRelationRepository,
    ) -> None:
        if not isinstance(tagging_service, ChunkTaggingService):
            raise TypeError("tagging_service must be a ChunkTaggingService")
        if not callable(getattr(repository, "replace_chunk_relations", None)):
            raise TypeError("repository must provide replace_chunk_relations")
        self._tagging_service = tagging_service
        self._repository = repository

    async def tag_and_persist(
        self,
        document_ref: str,
        source_version: str,
        request: ChunkTaggingRequest,
    ) -> ChunkTaggingRun:
        run = await self._tagging_service.tag_chunk(request)
        await self._repository.replace_chunk_relations(
            document_ref,
            source_version,
            tuple(item.paragraph.paragraph_id for item in request.paragraphs),
            run.relations,
        )
        return run
