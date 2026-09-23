from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from saxophone.cli.topic_input_vl import (
    _execute_ingestion,
    _parser,
    build_input_vl_source,
    embedding_token_count,
)
from saxophone.ingestion import IngestionReport


def test_build_input_vl_source_preserves_headers_pages_and_captions(tmp_path) -> None:
    source = tmp_path / "document-header-chunks.json"
    source.write_text(
        json.dumps(
            [
                {
                    "header": "Major Triads",
                    "content": "A major triad contains three notes.\n\n"
                    "![Example](images/page-0028-01.jpg)",
                    "page_start": 28,
                    "page_end": 29,
                }
            ]
        ),
        encoding="utf-8",
    )
    captions = tmp_path / "image-caption-map.json"
    captions.write_text(
        json.dumps(
            {
                "matches": [
                    {
                        "asset": "images/page-0028-01.jpg",
                        "caption": "A major triad diagram.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    prepared = build_input_vl_source(
        source,
        document_ref="music-theory",
        access_scope="default",
        caption_map_path=captions,
    )

    assert prepared.source_version == prepared.source_hash
    assert len(prepared.chunks) == 1
    chunk = prepared.chunks[0]
    assert chunk.metadata == {
        "heading": "Major Triads",
        "heading_level": 2,
        "page_start": 28,
        "page_end": 29,
    }
    assert chunk.search_text.startswith("## Major Triads\n\n")
    assert len(prepared.paragraphs) == 1
    paragraph = prepared.paragraphs[0]
    assert paragraph.heading_path == ("Major Triads",)
    assert paragraph.image_refs == ("images/page-0028-01.jpg",)
    assert paragraph.image_captions == {
        "images/page-0028-01.jpg": "A major triad diagram."
    }


def test_build_input_vl_source_limit_changes_version_and_scope(tmp_path) -> None:
    source = tmp_path / "document-header-chunks.json"
    source.write_text(
        json.dumps(
            [
                {"header": "One", "content": "First.", "page_start": 1, "page_end": 1},
                {"header": "Two", "content": "Second.", "page_start": 2, "page_end": 2},
            ]
        ),
        encoding="utf-8",
    )

    pilot = build_input_vl_source(
        source,
        document_ref="music-theory-pilot",
        access_scope="pilot",
        limit=1,
    )
    full = build_input_vl_source(
        source,
        document_ref="music-theory-full",
        access_scope="default",
    )

    assert len(pilot.chunks) == 1
    assert len(full.chunks) == 2
    assert pilot.source_version != full.source_version
    assert pilot.chunks[0].access_scope == "pilot"
    assert full.chunks[0].access_scope == "default"


def test_build_input_vl_source_splits_oversized_embedding_chunks(tmp_path) -> None:
    source = tmp_path / "document-header-chunks.json"
    source.write_text(
        json.dumps(
            [
                {
                    "header": "Large appendix",
                    "content": "\n\n".join(
                        f"Paragraph {index}: " + ("music theory " * 250)
                        for index in range(40)
                    ),
                    "page_start": 291,
                    "page_end": 297,
                }
            ]
        ),
        encoding="utf-8",
    )

    prepared = build_input_vl_source(
        source,
        document_ref="large-appendix",
        access_scope="default",
    )

    assert len(prepared.chunks) > 1
    assert all(chunk.metadata["source_heading"] == "Large appendix" for chunk in prepared.chunks)
    assert [chunk.metadata["part_index"] for chunk in prepared.chunks] == list(
        range(1, len(prepared.chunks) + 1)
    )
    assert all(chunk.metadata["part_count"] == len(prepared.chunks) for chunk in prepared.chunks)
    assert all(embedding_token_count(chunk.search_text) <= 8000 for chunk in prepared.chunks)


def test_parser_supports_ingest_only_mode() -> None:
    default_args = _parser().parse_args([])
    ingest_only_args = _parser().parse_args(["--ingest-only"])

    assert default_args.ingest_only is False
    assert ingest_only_args.ingest_only is True


def test_ingest_only_skips_question_answering(tmp_path, capsys) -> None:
    prepared = _prepared_source(tmp_path)
    facade = _RecordingFacade(_report(indexed=True))

    asyncio.run(
        _execute_ingestion(
            prepared,
            facade=facade,
            model_profile="text-embedding-3-small",
            question=None,
        )
    )

    assert len(facade.ingestion_requests) == 1
    assert facade.questions == []
    output = capsys.readouterr().out
    assert '"mode": "ingest-only"' in output
    assert '"answer_generated": false' in output


def test_ingest_only_rejects_incomplete_index(tmp_path) -> None:
    prepared = _prepared_source(tmp_path)
    facade = _RecordingFacade(_report(indexed=False, errors=("vector sync failed",)))

    with pytest.raises(RuntimeError, match="vector sync failed"):
        asyncio.run(
            _execute_ingestion(
                prepared,
                facade=facade,
                model_profile="text-embedding-3-small",
                question=None,
            )
        )

    assert facade.questions == []


def test_ingest_only_reports_warning_without_traceback_for_busy_chunks(
    tmp_path,
    capsys,
) -> None:
    prepared = _prepared_source(tmp_path)
    facade = _RecordingFacade(
        _report(
            indexed=False,
            warnings=("skipped 1 chunk(s) already being processed",),
        )
    )

    asyncio.run(
        _execute_ingestion(
            prepared,
            facade=facade,
            model_profile="text-embedding-3-small",
            question=None,
        )
    )

    output = capsys.readouterr().out
    assert '"incomplete"' in output
    assert '"indexed": false' in output
    assert "skipped 1 chunk(s) already being processed" in output
    assert facade.questions == []


def _prepared_source(tmp_path):
    source = tmp_path / "document-header-chunks.json"
    source.write_text(
        json.dumps(
            [
                {
                    "header": "Major Triads",
                    "content": "A major triad contains three notes.",
                    "page_start": 28,
                    "page_end": 28,
                }
            ]
        ),
        encoding="utf-8",
    )
    return build_input_vl_source(
        source,
        document_ref="music-theory-pilot",
        access_scope="default",
    )


def _report(
    *,
    indexed: bool,
    errors: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
) -> IngestionReport:
    return IngestionReport(
        document_ref="music-theory-pilot",
        source_version="source-v1",
        chunk_count=1,
        paragraph_count=1,
        tagged_paragraph_count=1,
        failed_paragraph_count=0,
        embedded_count=1,
        reused_embedding_count=0,
        skipped_count=0,
        index_version="index-v1",
        indexed=indexed,
        warnings=warnings,
        errors=errors,
    )


class _RecordingFacade:
    def __init__(self, report: IngestionReport) -> None:
        self._report = report
        self.ingestion_requests: list[object] = []
        self.questions: list[object] = []

    async def ingest_document(self, request):
        self.ingestion_requests.append(request)
        return self._report

    async def answer_question(self, request):
        self.questions.append(request)
        return SimpleNamespace()
