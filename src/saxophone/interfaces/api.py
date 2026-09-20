"""FastAPI inbound adapter for retrieval and chat use cases."""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from saxophone.chat.models import ChatResult
from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.documents.ports import ArtifactRepository
from saxophone.extraction.models import PdfExtractionRequest, PdfExtractionResult
from saxophone.ingestion.models import ChunkIndexRecord, IngestionCommand, IngestionReport
from saxophone.ingestion.use_cases import IndexDocument
from saxophone.retrieval.models import EvidenceBundle
from saxophone.workflows.process_document import ProcessDocument


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=100)
    filters: dict[str, object] | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=100)
    filters: dict[str, object] | None = None


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


class IngestionChunkRequest(BaseModel):
    chunk_id: str = Field(min_length=1)
    search_text: str = Field(min_length=1)
    embedding: list[float] = Field(min_length=1)
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
    artifact_repository: ArtifactRepository | None = None,
    index_document: IndexDocument | None = None,
) -> APIRouter:
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
        workflow = process_workflow
        if workflow is None and pdf_extractor is not None:
            raise HTTPException(
                status_code=503,
                detail="document processing capability is not configured",
            )
        if workflow is None:
            raise HTTPException(status_code=503, detail="extraction capability is not configured")
        normalized_ref = _normalized_text(document_ref, "document_ref")
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
        normalized_ref = _normalized_text(document_ref, "document_ref")
        payload = await file.read()
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

    @router.post("/documents/{document_ref}/ingest")
    async def ingest_document(
        document_ref: str,
        request: DocumentIngestionRequest,
    ) -> dict[str, object]:
        if index_document is None:
            raise HTTPException(status_code=503, detail="ingestion capability is not configured")
        normalized_ref = _normalized_text(document_ref, "document_ref")
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
            ChunkIndexRecord(
                chunk_id=record.chunk_id,
                document_ref=normalized_ref,
                source_version=request.source_version,
                search_text=record.search_text,
                embedding=tuple(record.embedding),
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
    }


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
