"""Workflow orchestration contracts for the Saxophone backend."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ingest_extracted_document import IngestExtractedDocument
    from .pdf_layout_extraction import load_layout_pages, run_extraction, start_extraction
    from .pdf_layout_jobs import PdfLayoutArtifactPaths, PdfLayoutJobNotFound, PdfLayoutJobStore
    from .process_document import ProcessAndPersistDocument, ProcessDocument


_CORE_EXPORTS = {
    "IngestExtractedDocument": (".ingest_extracted_document", "IngestExtractedDocument"),
    "ProcessAndPersistDocument": (".process_document", "ProcessAndPersistDocument"),
    "ProcessDocument": (".process_document", "ProcessDocument"),
}


_LAYOUT_EXPORTS = {
    "PdfLayoutArtifactPaths": (".pdf_layout_jobs", "PdfLayoutArtifactPaths"),
    "PdfLayoutJobNotFound": (".pdf_layout_jobs", "PdfLayoutJobNotFound"),
    "PdfLayoutJobStore": (".pdf_layout_jobs", "PdfLayoutJobStore"),
    "load_layout_pages": (".pdf_layout_extraction", "load_layout_pages"),
    "run_extraction": (".pdf_layout_extraction", "run_extraction"),
    "start_extraction": (".pdf_layout_extraction", "start_extraction"),
}


def __getattr__(name: str) -> object:
    """Load workflow implementations only when a caller requests them."""

    exports = {**_CORE_EXPORTS, **_LAYOUT_EXPORTS}
    try:
        module_name, attribute_name = exports[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


__all__ = [
    "ProcessDocument",
    "ProcessAndPersistDocument",
    "IngestExtractedDocument",
]
