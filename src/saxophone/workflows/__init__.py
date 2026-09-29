"""Workflow orchestration contracts for the Saxophone backend."""

from importlib import import_module
from typing import TYPE_CHECKING

from .ingest_extracted_document import IngestExtractedDocument
from .process_document import ProcessAndPersistDocument, ProcessDocument

if TYPE_CHECKING:
    from .pdf_layout_extraction import load_layout_pages, run_extraction, start_extraction
    from .pdf_layout_jobs import PdfLayoutArtifactPaths, PdfLayoutJobNotFound, PdfLayoutJobStore


_LAYOUT_EXPORTS = {
    "PdfLayoutArtifactPaths": (".pdf_layout_jobs", "PdfLayoutArtifactPaths"),
    "PdfLayoutJobNotFound": (".pdf_layout_jobs", "PdfLayoutJobNotFound"),
    "PdfLayoutJobStore": (".pdf_layout_jobs", "PdfLayoutJobStore"),
    "load_layout_pages": (".pdf_layout_extraction", "load_layout_pages"),
    "run_extraction": (".pdf_layout_extraction", "run_extraction"),
    "start_extraction": (".pdf_layout_extraction", "start_extraction"),
}


def __getattr__(name: str) -> object:
    """Load the optional PDF layout workflow only when a caller requests it."""

    try:
        module_name, attribute_name = _LAYOUT_EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


__all__ = [
    "ProcessDocument",
    "ProcessAndPersistDocument",
    "IngestExtractedDocument",
    "PdfLayoutJobNotFound",
    "PdfLayoutJobStore",
    "PdfLayoutArtifactPaths",
    "run_extraction",
    "start_extraction",
    "load_layout_pages",
]
