"""Contracts for provider output normalization used by the PDF viewer."""

from __future__ import annotations

from saxophone.extraction.layout import (
    RAW_PDF_RASTER_SPACE,
    is_raw_pdf_raster_space,
    normalize_blocks,
)


def test_normalize_blocks_keeps_only_valid_source_space_bbox() -> None:
    payload = {
        "parsing_res_list": [
            {
                "block_id": "text-1",
                "block_label": "text",
                "block_content": "Harmony",
                "source_bbox": [1, 2, 11, 22],
            },
            {
                "block_id": "invalid",
                "source_bbox": [1, 2, 1, 22],
                "bbox": [9, 9, 99, 99],
            },
            "not-a-block",
        ]
    }

    assert normalize_blocks(payload) == [
        {
            "id": "text-1",
            "order": 1,
            "label": "text",
            "text": "Harmony",
            "bbox": [1.0, 2.0, 11.0, 22.0],
        },
        {
            "id": "invalid",
            "order": 2,
            "label": "unknown",
            "text": "",
            "bbox": None,
        },
    ]


def test_normalize_blocks_rejects_boolean_and_non_finite_coordinates() -> None:
    payload = {
        "parsing_res_list": [
            {"source_bbox": [True, 1, 2, 3]},
            {"source_bbox": [1, 2, float("inf"), 4]},
        ]
    }

    assert normalize_blocks(payload) == [
        {"id": 0, "order": 1, "label": "unknown", "text": "", "bbox": None},
        {"id": 1, "order": 2, "label": "unknown", "text": "", "bbox": None},
    ]


def test_layout_coordinate_space_name_is_stable() -> None:
    assert RAW_PDF_RASTER_SPACE == "raw_pdf_raster_pixels"


def test_raw_pdf_raster_space_requires_identity_transform() -> None:
    assert is_raw_pdf_raster_space(
        {"name": RAW_PDF_RASTER_SPACE, "transform_to_source": "identity"}
    )
    assert not is_raw_pdf_raster_space(
        {"name": RAW_PDF_RASTER_SPACE, "transform_to_source": "scaled"}
    )
    assert not is_raw_pdf_raster_space(None)
