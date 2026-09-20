# Iteration 141 — Hợp đồng số hữu hạn cho layout OCR

## Mục tiêu

Khóa biên legacy `canonicalize_raw_pdf_layout()` để dữ liệu hình học không hữu hạn
không thể được gắn nhãn là tọa độ PDF nguồn và không thể làm hỏng metadata kích thước
trang.

## Thay đổi

- `_source_bbox()` từ chối `NaN`, `+Infinity` và `-Infinity` trước khi sao chép
  `block_bbox` sang `source_bbox`.
- `_valid_dimension()` yêu cầu `width` và `height` là số hữu hạn, dương và không
  phải boolean.
- Bổ sung kiểm thử hồi quy cho ba dạng bbox không hữu hạn và cả hai kích thước trang.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_layout_geometry.py tests/test_phase_3_extraction_contract.py`
  → **22 passed**.
- Thay đổi này chỉ harden boundary geometry; không thay đổi coordinate space hợp lệ
  hoặc hành vi bbox hữu hạn đang có.
- Live model-service smoke và production parity vẫn chưa thể xác minh vì checkout
  chưa có endpoint, credential và catalog production thật.

## Kết luận

Tiêu chí finite-number của extraction hiện được bảo vệ ở cả DTO `ExtractionCoordinate`
và legacy layout canonicalizer trước khi dữ liệu được dùng cho viewer/persistence.
