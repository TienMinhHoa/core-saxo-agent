from __future__ import annotations

from pathlib import Path

from music_rag.chroma_chunks import load_chunk_records
from music_rag.util import sha256_bytes


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "golden" / "chroma_sidecar"


def test_header_chunk_sidecar_preserves_source_provenance_and_validated_image_metadata() -> None:
    """Lock the current Chroma sidecar contract before ingestion is split out."""
    records = load_chunk_records(
        FIXTURE_DIR / "header_chunks.json",
        extraction_dir=FIXTURE_DIR,
        vlm_results_path=FIXTURE_DIR / "figure-vlm-results.jsonl",
    )

    assert len(records) == 1
    record = records[0]
    assert record["chunk_index"] == 0
    assert record["header"] == "Chương 1: Nhịp điệu"
    assert record["content"].startswith("Nhịp điệu giữ mạch")
    assert record["search_text"] == "Chương 1: Nhịp điệu Nhịp điệu giữ mạch cho bản nhạc."
    assert record["page_start"] == 4
    assert record["page_end"] == 5
    assert record["all_image_refs"] == ["images/rhythm.png"]
    assert record["image_refs"] == ["images/rhythm.png"]
    assert record["content_hash"] == sha256_bytes(record["search_text"].encode("utf-8"))
    assert record["source_chunks"] == str((FIXTURE_DIR / "header_chunks.json").resolve())
    assert record["extraction_dir"] == str(FIXTURE_DIR.resolve())
    assert record["images"] == [{
        "asset_ref": "images/rhythm.png",
        "image_path": None,
        "figure_number": "Hình 1",
        "figure_title": "Mô hình nhịp",
        "caption": "Ví dụ nhịp 4/4",
        "summary": "Một ô nhịp bốn phách",
        "asset_type": "score",
    }]
