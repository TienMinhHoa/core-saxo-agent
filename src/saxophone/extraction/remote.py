"""Remote model-service adapter for the PDF extraction port."""

from __future__ import annotations

from collections.abc import Mapping

from saxophone.documents.models import ArtifactKind, ArtifactRef
from saxophone.platform.model_client import ModelClient, ModelRequest, ModelTask

from .models import PdfExtractionRequest, PdfExtractionResult


class RemotePdfExtractor:
    """Translate a typed extraction request into one validated model call."""

    def __init__(
        self,
        model_client: ModelClient,
        *,
        model: str,
        response_schema: str = "pdf-extraction-v1",
    ) -> None:
        if not model.strip():
            raise ValueError("model must not be blank")
        if not response_schema.strip():
            raise ValueError("response_schema must not be blank")
        self._model_client = model_client
        self._model = model
        self._response_schema = response_schema

    @property
    def model(self) -> str:
        """Return the configured remote model profile used for extraction."""
        return self._model

    async def extract(self, request: PdfExtractionRequest) -> PdfExtractionResult:
        response = await self._model_client.invoke(
            ModelRequest(
                model=self._model,
                task=ModelTask.PDF_EXTRACT,
                input={
                    "document_ref": request.document_ref,
                    "source_artifact_id": request.source.artifact_id,
                    "source_artifact_version": request.source.version,
                },
                metadata={
                    "source_version": request.source_version,
                    "correlation_id": request.correlation_id,
                    "model_profile": request.model_profile,
                },
                response_schema=self._response_schema,
            ),
        )
        if response.task is not ModelTask.PDF_EXTRACT:
            raise ValueError("model response task must be pdf_extract")
        if response.response_schema != self._response_schema:
            raise ValueError("model response schema does not match extraction contract")
        output = response.output
        return PdfExtractionResult(
            document_ref=request.document_ref,
            source_version=response.source_version,
            markdown=_required_artifact(output, "markdown"),
            layout=_required_artifact(output, "layout"),
            manifest=_required_artifact(output, "manifest"),
            coordinates=(),
            model_profile=request.model_profile,
        )


def _required_artifact(output: Mapping[str, object], name: str) -> ArtifactRef:
    value = output.get(name)
    if isinstance(value, ArtifactRef):
        return value
    if not isinstance(value, Mapping):
        raise ValueError(f"model output {name} must be an artifact mapping")
    try:
        kind = ArtifactKind(value["kind"])
        return ArtifactRef(
            artifact_id=value["artifact_id"],
            version=value["version"],
            kind=kind,
            media_type=value["media_type"],
            sha256=value["sha256"],
            size_bytes=value["size_bytes"],
        )
    except KeyError as error:
        raise ValueError(f"model output {name} is missing {error.args[0]}") from error
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"model output {name} has invalid artifact metadata: {error}"
        ) from error
