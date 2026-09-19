from __future__ import annotations

import unittest

from extracted.layout_geometry import canonicalize_raw_pdf_layout


class LayoutGeometryTest(unittest.TestCase):
    def _payload(self, *, orientation: bool = False, unwarping: bool = False) -> dict:
        return {
            "width": 100,
            "height": 200,
            "doc_preprocessor_res": {
                "model_settings": {
                    "use_doc_orientation_classify": orientation,
                    "use_doc_unwarping": unwarping,
                }
            },
            "parsing_res_list": [
                {"block_bbox": [1, 2, 30, 40], "block_content": "source text"}
            ],
        }

    def test_raw_pdf_layout_copies_bbox_to_source_bbox_with_identity_contract(self) -> None:
        payload = self._payload()
        result = canonicalize_raw_pdf_layout(payload)
        self.assertEqual(result["parsing_res_list"][0]["source_bbox"], [1, 2, 30, 40])
        self.assertEqual(result["coordinate_space"]["name"], "raw_pdf_raster_pixels")
        self.assertEqual(result["coordinate_space"]["transform_to_source"], "identity")
        self.assertNotIn("source_bbox", payload["parsing_res_list"][0])

    def test_transformed_ocr_layout_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "use_doc_orientation_classify"):
            canonicalize_raw_pdf_layout(self._payload(orientation=True))
        with self.assertRaisesRegex(ValueError, "use_doc_unwarping"):
            canonicalize_raw_pdf_layout(self._payload(unwarping=True))

    def test_missing_preprocessor_proof_is_rejected(self) -> None:
        payload = self._payload()
        del payload["doc_preprocessor_res"]
        with self.assertRaisesRegex(ValueError, "Thiếu doc_preprocessor_res"):
            canonicalize_raw_pdf_layout(payload)
