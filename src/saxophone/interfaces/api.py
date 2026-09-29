"""FastAPI inbound adapter for retrieval and chat use cases."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import re
from contextlib import suppress
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from saxophone.agent.contracts import AgentQuestion
from saxophone.agent.events import AgentEvent, AgentEventType
from saxophone.agent.langchain_callbacks import AgentEventCallbackHandler
from saxophone.agent.streaming import AgentRunManager
from saxophone.chat import ChatResult, ImageArtifactGate
from saxophone.documents import (
    ArtifactKind,
    ArtifactRef,
    ArtifactRepository,
    ImageArtifactResolver,
    is_image_media_type,
    is_safe_document_reference,
    is_safe_relative_image_reference,
)
from saxophone.extraction import PdfExtractionRequest, PdfExtractionResult
from saxophone.ingestion import IndexDocument, IndexInputRecord, IngestionCommand, IngestionReport
from saxophone.retrieval import EvidenceBundle
from saxophone.interfaces.agent_stream import iter_agent_events

if TYPE_CHECKING:
    from saxophone.workflows import IngestExtractedDocument, ProcessAndPersistDocument, ProcessDocument


_AGENT_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=100)
    filters: dict[str, object] | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=100)
    filters: dict[str, object] | None = None


class AgentChatMessageRequest(BaseModel):
    question: str = Field(min_length=1)
    filters: dict[str, object] | None = None
    chunk_limit: int = Field(default=10, ge=1, le=100)
    max_paragraphs: int = Field(default=20, ge=1, le=100)
    max_tokens: int = Field(default=4000, ge=1, le=100_000)


class ArtifactRequest(BaseModel):
    artifact_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    kind: ArtifactKind
    media_type: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class DocumentProcessRequest(BaseModel):
    source: ArtifactRequest
    source_version: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    model_profile: str = Field(min_length=1)


class DocumentProcessAndIngestRequest(DocumentProcessRequest):
    chunking_profile: str = Field(min_length=1)
    embedding_profile: str = Field(min_length=1)
    index_profile: str = Field(min_length=1)
    access_scope: str = Field(min_length=1)
    tagging_profile: str = Field(default="none-v1", min_length=1)
    resolution_profile: str = Field(default="none-v1", min_length=1)


class IngestionChunkRequest(BaseModel):
    chunk_id: str = Field(min_length=1)
    search_text: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class DocumentIngestionRequest(BaseModel):
    source_version: str = Field(min_length=1)
    chunking_profile: str = Field(min_length=1)
    tagging_profile: str = Field(min_length=1)
    embedding_profile: str = Field(min_length=1)
    index_profile: str = Field(min_length=1)
    access_scope: str = Field(min_length=1)
    records: list[IngestionChunkRequest]


def build_capability_router(
    *,
    retrieve_evidence: Any = None,
    answer_question: Any = None,
    pdf_extractor: Any = None,
    process_workflow: ProcessDocument | None = None,
    process_and_persist_workflow: ProcessAndPersistDocument | None = None,
    artifact_repository: ArtifactRepository | None = None,
    image_artifact_resolver: ImageArtifactResolver | None = None,
    image_artifact_gate: ImageArtifactGate | None = None,
    index_document: IndexDocument | None = None,
    ingest_extracted_document: IngestExtractedDocument | None = None,
    max_upload_bytes: int = 200 * 1024 * 1024,
) -> APIRouter:
    if isinstance(max_upload_bytes, bool) or not isinstance(max_upload_bytes, int):
        raise ValueError("max_upload_bytes must be a positive integer")
    if max_upload_bytes <= 0:
        raise ValueError("max_upload_bytes must be a positive integer")
    router = APIRouter(prefix="/api/v1")

    @router.post("/retrieval/evidence")
    async def retrieve(request: QueryRequest) -> dict[str, object]:
        if retrieve_evidence is None:
            raise HTTPException(status_code=503, detail="retrieval capability is not configured")
        query = _normalized_text(request.query, "query")
        evidence: EvidenceBundle = await retrieve_evidence.execute(
            query, filters=request.filters, limit=request.limit
        )
        return _evidence_response(evidence)

    @router.post("/search")
    async def search(request: QueryRequest) -> dict[str, object]:
        """Expose the architecture-plan name over the retrieval facade."""
        return await retrieve(request)

    @router.post("/chat")
    async def chat(request: ChatRequest) -> dict[str, object]:
        if answer_question is None:
            raise HTTPException(status_code=503, detail="chat capability is not configured")
        question = _normalized_text(request.question, "question")
        result: ChatResult = await answer_question.execute(
            question, filters=request.filters, limit=request.limit
        )
        return _chat_response(result)

    @router.post("/documents/{document_ref}/process")
    async def process_document(
        document_ref: str,
        request: DocumentProcessRequest,
    ) -> dict[str, object]:
        workflow = process_and_persist_workflow or process_workflow
        if workflow is None and pdf_extractor is not None:
            raise HTTPException(
                status_code=503,
                detail="document processing capability is not configured",
            )
        if workflow is None:
            raise HTTPException(status_code=503, detail="extraction capability is not configured")
        normalized_ref = _normalized_reference(document_ref, "document_ref")
        _require_safe_document_reference(normalized_ref)
        try:
            result: PdfExtractionResult = await workflow.execute(
                PdfExtractionRequest(
                    document_ref=normalized_ref,
                    source=ArtifactRef(**request.source.model_dump()),
                    source_version=request.source_version,
                    correlation_id=request.correlation_id,
                    model_profile=request.model_profile,
                ),
            )
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return _extraction_response(result)

    @router.post("/documents/{document_ref}/source", status_code=201)
    async def upload_source(document_ref: str, file: UploadFile = File(...)) -> dict[str, object]:
        if artifact_repository is None:
            raise HTTPException(status_code=503, detail="document storage is not configured")
        if file.content_type != "application/pdf":
            raise HTTPException(
                status_code=415,
                detail="uploaded file must have media type application/pdf",
            )
        normalized_ref = _normalized_reference(document_ref, "document_ref")
        _require_safe_document_reference(normalized_ref)
        payload = await _read_bounded_upload(file, max_upload_bytes)
        if b"%PDF-" not in payload[:1024]:
            raise HTTPException(
                status_code=422,
                detail="uploaded file does not have a valid PDF signature",
            )
        artifact = ArtifactRef(
            artifact_id=f"{normalized_ref}/source",
            version="v1",
            kind=ArtifactKind.SOURCE_PDF,
            media_type="application/pdf",
            sha256=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
        )
        try:
            await artifact_repository.put(artifact, payload)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return _artifact_response(artifact)

    @router.get("/assets/{asset_ref:path}")
    async def get_asset(asset_ref: str) -> Response:
        if (
            image_artifact_resolver is None
            or artifact_repository is None
            or image_artifact_gate is None
        ):
            raise HTTPException(
                status_code=503,
                detail="asset resolution capability is not configured",
            )
        normalized_ref = _normalized_reference(asset_ref, "asset_ref")
        if not is_safe_relative_image_reference(normalized_ref):
            raise HTTPException(status_code=422, detail="unsafe image reference")
        try:
            await image_artifact_gate.validate((normalized_ref,))
            artifact = await image_artifact_resolver.resolve(normalized_ref)
            if artifact.kind is not ArtifactKind.IMAGE:
                raise ValueError("resolved artifact kind must be IMAGE")
            if not is_image_media_type(artifact.media_type):
                raise ValueError("resolved image artifact must have an image media type")
            payload = await artifact_repository.get(artifact)
        except (
            FileNotFoundError,
            FileExistsError,
            IsADirectoryError,
            NotADirectoryError,
        ) as error:
            raise HTTPException(status_code=404, detail="asset not found") from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail="asset access denied") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return Response(content=payload, media_type=artifact.media_type)

    @router.post("/documents/{document_ref}/process-and-ingest")
    async def process_and_ingest_document(
        document_ref: str,
        request: DocumentProcessAndIngestRequest,
    ) -> dict[str, object]:
        if process_and_persist_workflow is None:
            raise HTTPException(
                status_code=503,
                detail="document persistence capability is not configured",
            )
        if ingest_extracted_document is None:
            raise HTTPException(
                status_code=503,
                detail="extracted document ingestion capability is not configured",
            )
        normalized_ref = _normalized_reference(document_ref, "document_ref")
        _require_safe_document_reference(normalized_ref)
        try:
            result = await process_and_persist_workflow.execute(
                PdfExtractionRequest(
                    document_ref=normalized_ref,
                    source=ArtifactRef(**request.source.model_dump()),
                    source_version=request.source_version,
                    correlation_id=request.correlation_id,
                    model_profile=request.model_profile,
                ),
            )
            report = await ingest_extracted_document.execute(
                result,
                chunking_profile=request.chunking_profile,
                embedding_profile=request.embedding_profile,
                index_profile=request.index_profile,
                access_scope=request.access_scope,
                tagging_profile=request.tagging_profile,
                resolution_profile=request.resolution_profile,
            )
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"extraction": _extraction_response(result), "ingestion": _ingestion_response(report)}

    @router.post("/documents/{document_ref}/ingest")
    async def ingest_document(
        document_ref: str,
        request: DocumentIngestionRequest,
    ) -> dict[str, object]:
        if index_document is None:
            raise HTTPException(status_code=503, detail="ingestion capability is not configured")
        normalized_ref = _normalized_reference(document_ref, "document_ref")
        _require_safe_document_reference(normalized_ref)
        command = IngestionCommand(
            document_ref=normalized_ref,
            source_version=request.source_version,
            chunking_profile=request.chunking_profile,
            tagging_profile=request.tagging_profile,
            embedding_profile=request.embedding_profile,
            index_profile=request.index_profile,
            access_scope=request.access_scope,
        )
        records = tuple(
            IndexInputRecord(
                chunk_id=record.chunk_id,
                document_ref=normalized_ref,
                source_version=request.source_version,
                search_text=record.search_text,
                embedding_profile=request.embedding_profile,
                access_scope=request.access_scope,
                metadata=record.metadata,
            )
            for record in request.records
        )
        try:
            report: IngestionReport = await index_document.execute(command, records)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return _ingestion_response(report)

    return router


async def _finish_agent_stream_run(
    runner: object,
    manager: AgentRunManager,
    request: AgentChatMessageRequest,
    run_id: str,
    callback: AgentEventCallbackHandler,
) -> None:
    """Run the injected agent and close its public event stream safely."""

    try:
        question = _agent_question(request)
        run_method = getattr(runner, "run", None) or getattr(runner, "execute", None)
        if not callable(run_method):
            raise TypeError("agent runner must provide async run")
        result = run_method(
            question,
            run_id=run_id,
            callbacks=[callback],
        )
        if inspect.isawaitable(result):
            result = await result
        outcome_value = getattr(result, "outcome", None)
        outcome = getattr(outcome_value, "value", outcome_value)
        outcome = outcome.strip() if isinstance(outcome, str) and outcome.strip() else None
        if outcome == "failed":
            await manager.publish(
                AgentEvent(
                    AgentEventType.RUN_FAILED,
                    run_id=run_id,
                    error_code="agent_failed",
                )
            )
        else:
            await manager.publish(
                AgentEvent(
                    AgentEventType.RUN_COMPLETED,
                    run_id=run_id,
                    status=outcome or "completed",
                )
            )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        with suppress(KeyError, ValueError):
            if await manager.is_active(run_id):
                await manager.publish(
                    AgentEvent(
                        AgentEventType.RUN_FAILED,
                        run_id=run_id,
                        error_code=error.__class__.__name__,
                    )
                )


def _agent_question(request: AgentChatMessageRequest) -> AgentQuestion:
    filters = request.filters or {}
    if any(not isinstance(value, str) for value in filters.values()):
        raise ValueError("agent stream filters must contain string values")
    return AgentQuestion(
        request.question,
        filters=filters,
        context_limit=request.max_tokens,
    )


def _optional_run_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not _AGENT_RUN_ID_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=400, detail="X-Agent-Run-ID is invalid")
    return normalized


def _parse_last_event_id(value: str | None) -> int:
    if value is None or not value.strip():
        return 0
    try:
        parsed = int(value)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Last-Event-ID is invalid") from error
    if parsed < 0:
        raise HTTPException(status_code=400, detail="Last-Event-ID is invalid")
    return parsed


def build_agent_chat_router(
    *,
    agent_chat: Any = None,
    agent_runner: Any = None,
    agent_run_manager: AgentRunManager | None = None,
    assets_root: Path | None = None,
    image_artifact_resolver: ImageArtifactResolver | None = None,
    image_artifact_gate: ImageArtifactGate | None = None,
) -> APIRouter:
    """Serve the browser chat console and its grounded-answer JSON boundary."""

    root = assets_root or Path(__file__).with_name("api") / "assets" / "chat"
    if not isinstance(root, Path):
        raise TypeError("assets_root must be a Path")
    router = APIRouter()
    assets = {
        "chat.css": (root / "chat.css", "text/css"),
        "chat.js": (root / "chat.js", "application/javascript"),
    }
    active_runs: dict[str, asyncio.Task[None]] = {}

    @router.get("/agent/chat", include_in_schema=False)
    async def agent_chat_page() -> FileResponse:
        return FileResponse(root / "index.html", media_type="text/html")

    @router.get("/agent/chat/assets/{asset_name}", include_in_schema=False)
    async def agent_chat_asset(asset_name: str) -> FileResponse:
        asset = assets.get(asset_name)
        if asset is None:
            raise HTTPException(status_code=404, detail="chat asset not found")
        path, media_type = asset
        return FileResponse(path, media_type=media_type)

    @router.post("/agent/chat/messages")
    async def agent_chat_message(
        request: AgentChatMessageRequest,
    ) -> dict[str, object]:
        question = _normalized_text(request.question, "question")
        if agent_chat is None:
            raise HTTPException(
                status_code=503,
                detail="agent chat capability is not configured",
            )
        # Keep the legacy request DTO behind this compatibility route.
        from saxophone.retrieval.question_retrieval import QuestionRequest

        result = await agent_chat.answer(
            QuestionRequest(
                question,
                filters=request.filters,
                chunk_limit=request.chunk_limit,
                max_paragraphs=request.max_paragraphs,
                max_tokens=request.max_tokens,
            )
        )
        return await _agent_chat_response(
            result,
            image_artifact_resolver=image_artifact_resolver,
            image_artifact_gate=image_artifact_gate,
        )

    @router.post("/agent/chat/stream")
    async def agent_chat_stream(
        request: AgentChatMessageRequest,
        run_id_header: str | None = Header(default=None, alias="X-Agent-Run-ID"),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        """Stream safe progress events for a new or replayed agent run."""

        if agent_run_manager is None:
            raise HTTPException(
                status_code=503,
                detail="agent streaming capability is not configured",
            )
        after_sequence = _parse_last_event_id(last_event_id)
        requested_run_id = _optional_run_id(run_id_header)
        run_task: asyncio.Task[None] | None = None

        if requested_run_id is not None:
            try:
                await agent_run_manager.history(requested_run_id)
            except KeyError as error:
                raise HTTPException(status_code=404, detail="agent run not found") from error
            run_id = requested_run_id
        else:
            if agent_runner is None:
                raise HTTPException(
                    status_code=503,
                    detail="agent streaming capability is not configured",
                )
            try:
                _agent_question(request)
            except ValueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            run_id = await agent_run_manager.start()
            callback = AgentEventCallbackHandler(run_id=run_id, sink=agent_run_manager)
            run_task = asyncio.create_task(
                _finish_agent_stream_run(
                    agent_runner,
                    agent_run_manager,
                    request,
                    run_id,
                    callback,
                )
            )
            active_runs[run_id] = run_task

        async def event_body():
            try:
                async for frame in iter_agent_events(
                    agent_run_manager,
                    run_id,
                    after_sequence=after_sequence,
                ):
                    yield frame
            except asyncio.CancelledError:
                if await agent_run_manager.is_active(run_id):
                    await agent_run_manager.cancel(run_id)
                if run_task is not None and not run_task.done():
                    run_task.cancel()
                raise
            finally:
                if run_task is not None:
                    active_runs.pop(run_id, None)
                    if not run_task.done():
                        run_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await run_task

        return StreamingResponse(
            event_body(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Agent-Run-ID": run_id,
            },
        )

    return router


def _evidence_response(evidence: EvidenceBundle) -> dict[str, object]:
    return {
        "query": evidence.query,
        "retrieval_version": evidence.retrieval_version,
        "selected_refs": list(evidence.selected_refs),
        "source_texts": dict(evidence.source_texts),
        "image_refs": list(evidence.image_refs),
        "insufficiency_reason": evidence.insufficiency_reason,
    }


def _chat_response(result: ChatResult) -> dict[str, object]:
    return {
        "status": result.status.value,
        "answer": result.answer,
        "citations": list(result.citations),
        "evidence_bundle_ref": result.evidence_bundle_ref,
        "model_version": result.model_version,
        "token_usage": dict(result.token_usage),
        "cost": result.cost,
        "insufficiency_reason": result.insufficiency_reason,
    }


async def _agent_chat_response(
    result: object,
    *,
    image_artifact_resolver: ImageArtifactResolver | None = None,
    image_artifact_gate: ImageArtifactGate | None = None,
) -> dict[str, object]:
    sources = tuple(getattr(result, "sources", ()))
    if not sources:
        sources = _agent_run_sources(result)
    image_validation_enabled = image_artifact_gate is not None
    response: dict[str, object] = {
        "status": _enum_value(getattr(result, "status", getattr(result, "outcome", None))),
        "answer": getattr(result, "answer", None),
        "sources": [],
        "model_version": getattr(result, "model_version", None),
    }
    source_payloads: list[dict[str, object]] = []
    for index, source in enumerate(sources, start=1):
        source_payloads.append(
            await _source_response(
                source,
                citation=f"[{index}]",
                image_artifact_resolver=image_artifact_resolver,
                image_artifact_gate=image_artifact_gate,
                image_validation_enabled=image_validation_enabled,
            )
        )
    response["sources"] = source_payloads
    clarification = _clarification_response(getattr(result, "clarification", None))
    if clarification is not None:
        response["clarification"] = clarification
    return response


async def _source_response(
    source: object,
    *,
    citation: str,
    image_artifact_resolver: ImageArtifactResolver | None,
    image_artifact_gate: ImageArtifactGate | None,
    image_validation_enabled: bool,
) -> dict[str, object]:
    image_refs = tuple(getattr(source, "image_refs", ()))
    payload: dict[str, object] = {
        "citation": citation,
        "paragraph_ref": getattr(source, "paragraph_ref", ""),
        "chunk_id": getattr(source, "chunk_id", ""),
        "source": getattr(source, "source", ""),
        "page_start": getattr(source, "page_start", None),
        "page_end": getattr(source, "page_end", None),
        "image_refs": list(image_refs),
    }
    existing_errors = tuple(getattr(source, "image_errors", ()))
    if existing_errors:
        payload["image_errors"] = list(existing_errors)
    if not image_refs or not image_validation_enabled or image_artifact_gate is None:
        return payload

    captions = getattr(source, "image_captions", {})
    images: list[dict[str, str]] = []
    errors: list[str] = []
    for image_ref in image_refs:
        if not is_safe_relative_image_reference(image_ref):
            errors.append("image unavailable")
            continue
        try:
            if image_artifact_resolver is not None:
                artifact = await image_artifact_resolver.resolve(image_ref)
                if artifact.kind is not ArtifactKind.IMAGE:
                    raise ValueError("resolved artifact kind must be IMAGE")
                if not is_image_media_type(artifact.media_type):
                    raise ValueError("resolved image artifact must have an image media type")
            validated = await image_artifact_gate.validate((image_ref,))
            if image_ref not in validated:
                raise ValueError("image reference was not validated")
        except Exception:
            # Keep the source visible while suppressing an unusable asset.
            errors.append("image unavailable")
            continue
        caption = captions.get(image_ref) if isinstance(captions, Mapping) else None
        if not isinstance(caption, str) or not caption.strip():
            caption = _fallback_image_caption(image_ref)
        images.append(
            {
                "ref": image_ref,
                "url": f"/api/v1/assets/{quote(image_ref, safe='/')}",
                "caption": caption.strip(),
                "alt": f"Hình minh họa được trích từ nguồn {citation}",
            }
        )
    if images:
        payload["images"] = images
    if errors:
        payload["image_errors"] = errors
    return payload


def _fallback_image_caption(image_ref: str) -> str:
    name = image_ref.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    return stem.replace("_", " ").replace("-", " ").strip() or "Source image"


def _agent_run_sources(result: object) -> tuple[object, ...]:
    """Project a typed agent result into the legacy source response shape."""

    ledger = getattr(result, "ledger", None)
    synthesis = getattr(result, "synthesis", None)
    evidence = getattr(ledger, "evidence", ()) if ledger is not None else ()
    if not evidence or synthesis is None:
        return ()
    evidence_by_id = {item.evidence_id: item for item in evidence}
    image_ids = set(getattr(synthesis, "image_evidence_ids", ()))
    citation_items = tuple(getattr(synthesis, "citations", ()))
    ordered_ids = [citation.evidence_id for citation in citation_items]
    if not ordered_ids:
        ordered_ids.extend(getattr(synthesis, "used_evidence_ids", ()))
    sources: list[object] = []
    for evidence_id in dict.fromkeys(ordered_ids):
        item = evidence_by_id.get(evidence_id)
        if item is None:
            continue
        source_ref = item.source_ref or item.url or "web source"
        refs = item.image_refs if evidence_id in image_ids else ()
        sources.append(
            _source_from_evidence(
                item,
                source_ref=source_ref,
                image_refs=refs,
            )
        )
    return tuple(sources)


def _source_from_evidence(
    item: object,
    *,
    source_ref: str,
    image_refs: tuple[str, ...],
) -> object:
    from saxophone.chat.compatibility import AnswerSource

    return AnswerSource(
        paragraph_ref=getattr(item, "paragraph", ""),
        chunk_id=getattr(item, "chunk", ""),
        source=source_ref,
        page_start=getattr(item, "page", None),
        page_end=getattr(item, "page", None),
        image_refs=image_refs,
    )


def _clarification_response(value: object) -> dict[str, object] | None:
    """Expose only the bounded clarification choices at the API boundary."""

    if value is None:
        return None
    if isinstance(value, Mapping):
        question = value.get("question")
        options = value.get("options")
        reason_code = value.get("reason_code")
    else:
        question = getattr(value, "question", None)
        options = getattr(value, "options", None)
        reason_code = getattr(value, "reason_code", None)
    if not isinstance(question, str) or not question.strip():
        return None
    if isinstance(options, (str, bytes)) or not isinstance(options, (tuple, list)):
        return None
    normalized_options = tuple(
        option.strip()
        for option in options
        if isinstance(option, str) and option.strip()
    )
    if not normalized_options:
        return None
    if not isinstance(reason_code, str) or not reason_code.strip():
        return None
    return {
        "question": question.strip(),
        "options": list(dict.fromkeys(normalized_options)),
        "reason_code": reason_code.strip(),
    }


def _enum_value(value: object) -> str:
    candidate = getattr(value, "value", value)
    return candidate if isinstance(candidate, str) else str(candidate)


def _extraction_response(result: PdfExtractionResult) -> dict[str, object]:
    return {
        "document_ref": result.document_ref,
        "source_version": result.source_version,
        "model_profile": result.model_profile,
        "markdown": _artifact_response(result.markdown),
        "layout": _artifact_response(result.layout),
        "manifest": _artifact_response(result.manifest),
        "coordinates": [
            {
                "coordinate_space": coordinate.coordinate_space.value,
                "page_index": coordinate.page_index,
                "markdown_line_start": coordinate.markdown_line_start,
                "markdown_line_end": coordinate.markdown_line_end,
                "bbox": coordinate.bbox,
            }
            for coordinate in result.coordinates
        ],
    }


def _ingestion_response(report: IngestionReport) -> dict[str, object]:
    return {
        "document_ref": report.document_ref,
        "source_version": report.source_version,
        "chunk_count": report.chunk_count,
        "paragraph_count": report.paragraph_count,
        "tagged_paragraph_count": report.tagged_paragraph_count,
        "failed_paragraph_count": report.failed_paragraph_count,
        "embedded_count": report.embedded_count,
        "reused_embedding_count": report.reused_embedding_count,
        "skipped_count": report.skipped_count,
        "index_version": report.index_version,
        "indexed": report.indexed,
        "warnings": list(report.warnings),
        "errors": list(report.errors),
    }


def _artifact_response(artifact: ArtifactRef) -> dict[str, object]:
    return {
        "artifact_id": artifact.artifact_id,
        "version": artifact.version,
        "kind": artifact.kind.value,
        "media_type": artifact.media_type,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
    }


def _normalized_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail=f"{field_name} must not be blank")
    return normalized


def _normalized_reference(value: str, field_name: str) -> str:
    """Normalize a route reference without accepting non-canonical whitespace."""

    normalized = _normalized_text(value, field_name)
    if normalized != value:
        raise HTTPException(status_code=422, detail=f"unsafe {field_name}")
    return normalized


def _require_safe_document_reference(document_ref: str) -> None:
    if not is_safe_document_reference(document_ref):
        raise HTTPException(status_code=422, detail="unsafe document_ref")


async def _read_bounded_upload(file: UploadFile, max_upload_bytes: int) -> bytes:
    if max_upload_bytes <= 0:
        raise ValueError("max_upload_bytes must be positive")
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(min(1024 * 1024, max_upload_bytes - total + 1)):
        total += len(chunk)
        if total > max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"uploaded file exceeds maximum size of {max_upload_bytes} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)
