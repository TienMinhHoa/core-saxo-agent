"""FastAPI inbound adapter for retrieval and chat use cases."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from saxophone.chat.models import ChatResult
from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.extraction.models import PdfExtractionRequest, PdfExtractionResult
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


def build_capability_router(
    *,
    retrieve_evidence: Any = None,
    answer_question: Any = None,
    pdf_extractor: Any = None,
    process_workflow: ProcessDocument | None = None,
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
