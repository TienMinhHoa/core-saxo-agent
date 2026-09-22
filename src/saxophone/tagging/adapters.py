"""Remote model adapters for paragraph tagging tasks."""

from __future__ import annotations

from collections.abc import Mapping

from saxophone.platform.model_client import (
    ModelClient,
    ModelRequest,
    ModelTask,
    ModelValidationError,
)

from .models import (
    TagConflictResolution,
    TagConflictResolutionRequest,
    TagGenerationRequest,
    TagGenerationResult,
    TagResolution,
)
from .chunk_models import ChunkTaggingRequest, ChunkTaggingResult
from .ports import ChunkTagger, TagConflictResolver, TagGenerator


class RemoteChunkTagger(ChunkTagger):
    """Translate one validated chunk-tagging request into a model call."""

    def __init__(
        self,
        client: ModelClient,
        *,
        model: str,
        response_schema: str = "chunk-tagging-v1",
    ) -> None:
        if not model.strip():
            raise ValueError("model must not be blank")
        if not response_schema.strip():
            raise ValueError("response_schema must not be blank")
        self._client = client
        self._model = model.strip()
        self._response_schema = response_schema.strip()

    @property
    def model(self) -> str:
        return self._model

    async def tag(self, request: ChunkTaggingRequest) -> ChunkTaggingResult:
        response = await self._client.invoke(
            ModelRequest(
                model=self._model,
                task=ModelTask.CHUNK_TAGGING,
                input={
                    "chunk_id": request.chunk_id,
                    "paragraphs": [
                        {
                            "paragraph_id": item.paragraph.paragraph_id,
                            "text": item.paragraph.text,
                            "heading_path": list(item.paragraph.heading_path),
                            "existing_candidates": list(item.existing_candidates),
                            "previous_context": item.previous_context,
                            "next_context": item.next_context,
                            "image_context": list(item.image_context),
                        }
                        for item in request.paragraphs
                    ],
                },
                metadata={"chunk_id": request.chunk_id},
                response_schema=self._response_schema,
                idempotency_key=f"chunk-tag-{request.chunk_id}",
            ),
        )
        _validate_response(
            response.task,
            response.response_schema,
            ModelTask.CHUNK_TAGGING,
            self._response_schema,
        )
        try:
            output = response.output
            result = ChunkTaggingResult(
                chunk_id=_required_text(output, "chunk_id"),
                chunk_new_concepts=_required_string_list(output, "chunk_new_concepts"),
                paragraphs=_parse_chunk_paragraphs(output),
            )
            result.validate_against(request)
            return result
        except ModelValidationError:
            raise
        except (TypeError, ValueError) as exc:
            raise ModelValidationError(f"chunk tagging output violates contract: {exc}") from exc


class RemoteParagraphTagger(TagGenerator):
    """Translate one paragraph-tagging request into a validated model call."""

    def __init__(
        self,
        client: ModelClient,
        *,
        model: str,
        response_schema: str = "paragraph-tags-v1",
    ) -> None:
        if not model.strip():
            raise ValueError("model must not be blank")
        if not response_schema.strip():
            raise ValueError("response_schema must not be blank")
        self._client = client
        self._model = model.strip()
        self._response_schema = response_schema.strip()

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, request: TagGenerationRequest) -> TagGenerationResult:
        paragraph = request.paragraph
        response = await self._client.invoke(
            ModelRequest(
                model=self._model,
                task=ModelTask.PARAGRAPH_TAG,
                input={
                    "paragraph_id": paragraph.paragraph_id,
                    "text": paragraph.text,
                    "heading_path": list(paragraph.heading_path),
                    "image_refs": list(paragraph.image_refs),
                    "image_captions": dict(paragraph.image_captions),
                },
                metadata={"tagging_profile": request.tagging_profile},
                response_schema=self._response_schema,
                idempotency_key=f"tag-{paragraph.paragraph_id}-{request.tagging_profile}",
            ),
        )
        _validate_response(
            response.task,
            response.response_schema,
            ModelTask.PARAGRAPH_TAG,
            self._response_schema,
        )
        output = response.output
        paragraph_id = _required_text(output, "paragraph_id")
        raw_tags = output.get("tags")
        if not isinstance(raw_tags, list) or any(
            not isinstance(tag, str) for tag in raw_tags
        ):
            raise ModelValidationError(
                "paragraph tag response tags must be a list of strings"
            )
        if paragraph_id != paragraph.paragraph_id:
            raise ModelValidationError(
                "paragraph tag response paragraph_id does not match request"
            )
        return TagGenerationResult(
            paragraph_id, tuple(raw_tags), request.tagging_profile
        )


class RemoteTagConflictResolver(TagConflictResolver):
    """Translate existing-vs-new tag resolution through the model boundary."""

    def __init__(
        self,
        client: ModelClient,
        *,
        model: str,
        response_schema: str = "tag-resolution-v1",
    ) -> None:
        if not model.strip():
            raise ValueError("model must not be blank")
        if not response_schema.strip():
            raise ValueError("response_schema must not be blank")
        self._client = client
        self._model = model.strip()
        self._response_schema = response_schema.strip()

    @property
    def model(self) -> str:
        return self._model

    async def resolve(
        self, request: TagConflictResolutionRequest
    ) -> TagConflictResolution:
        response = await self._client.invoke(
            ModelRequest(
                model=self._model,
                task=ModelTask.TAG_RESOLVE,
                input={
                    "paragraph_id": request.paragraph_id,
                    "generated_tags": list(request.generated_tags),
                    "existing_tags": [
                        {"tag": candidate.tag, "examples": list(candidate.examples)}
                        for candidate in request.existing_tags
                    ],
                },
                metadata={"resolution_profile": request.resolution_profile},
                response_schema=self._response_schema,
                idempotency_key=f"resolve-{request.paragraph_id}-{request.resolution_profile}",
            ),
        )
        _validate_response(
            response.task,
            response.response_schema,
            ModelTask.TAG_RESOLVE,
            self._response_schema,
        )
        output = response.output
        paragraph_id = _required_text(output, "paragraph_id")
        if paragraph_id != request.paragraph_id:
            raise ModelValidationError(
                "tag resolution paragraph_id does not match request"
            )
        raw_resolutions = output.get("resolutions")
        if not isinstance(raw_resolutions, list):
            raise ModelValidationError("tag resolution resolutions must be a list")
        resolutions: list[TagResolution] = []
        for item in raw_resolutions:
            if not isinstance(item, Mapping):
                raise ModelValidationError("tag resolution item must be a mapping")
            try:
                resolutions.append(
                    TagResolution(
                        _required_text(item, "generated_tag"),
                        _required_text(item, "action"),
                        _required_text(item, "resolved_tag"),
                    )
                )
            except ModelValidationError:
                raise
            except ValueError as exc:
                raise ModelValidationError(str(exc)) from exc
        try:
            return TagConflictResolution(
                paragraph_id=paragraph_id,
                resolutions=tuple(resolutions),
                resolution_profile=request.resolution_profile,
                generated_tags=request.generated_tags,
                existing_tags=tuple(
                    candidate.tag for candidate in request.existing_tags
                ),
            )
        except ModelValidationError:
            raise
        except ValueError as exc:
            raise ModelValidationError(str(exc)) from exc


def _validate_response(
    task: ModelTask, schema: str, expected_task: ModelTask, expected_schema: str
) -> None:
    if task is not expected_task:
        raise ModelValidationError(f"model response task must be {expected_task.value}")
    if schema != expected_schema:
        raise ModelValidationError(
            "model response schema does not match tagging contract"
        )


def _required_text(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ModelValidationError(f"model output {name} must be non-blank")
    return value.strip()


def _required_string_list(payload: Mapping[str, object], name: str) -> tuple[str, ...]:
    value = payload.get(name)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ModelValidationError(f"chunk tagging output {name} must be a list of strings")
    return tuple(value)


def _parse_chunk_paragraphs(payload: Mapping[str, object]) -> tuple:
    from .chunk_models import ChunkParagraphTaggingResult, ChunkTaggingLabel
    from .models import ContentRole

    raw_paragraphs = payload.get("paragraphs")
    if not isinstance(raw_paragraphs, list):
        raise ModelValidationError("chunk tagging output paragraphs must be a list")
    parsed = []
    for item in raw_paragraphs:
        if not isinstance(item, Mapping):
            raise ModelValidationError("chunk tagging paragraph must be a mapping")
        raw_labels = item.get("labels")
        if not isinstance(raw_labels, list):
            raise ModelValidationError("chunk tagging labels must be a list")
        labels = []
        for raw_label in raw_labels:
            if not isinstance(raw_label, Mapping):
                raise ModelValidationError("chunk tagging label must be a mapping")
            raw_roles = raw_label.get("roles")
            if not isinstance(raw_roles, list):
                raise ModelValidationError("chunk tagging roles must be a list")
            try:
                labels.append(
                    ChunkTaggingLabel(
                        _required_text(raw_label, "generated_concept"),
                        _required_text(raw_label, "action"),
                        _required_text(raw_label, "resolved_concept"),
                        tuple(ContentRole(role) for role in raw_roles),
                    )
                )
            except (TypeError, ValueError) as exc:
                raise ModelValidationError(f"chunk tagging label is invalid: {exc}") from exc
        try:
            parsed.append(
                ChunkParagraphTaggingResult(
                    _required_text(item, "paragraph_ref"), tuple(labels), item.get("tagging_status", "completed")
                )
            )
        except ValueError as exc:
            raise ModelValidationError(f"chunk tagging paragraph is invalid: {exc}") from exc
    return tuple(parsed)
