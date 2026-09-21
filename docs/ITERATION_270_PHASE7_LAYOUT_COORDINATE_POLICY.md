# Iteration 270 — Chính sách coordinate-space thuộc extraction boundary

## Phạm vi

Tách quy tắc chấp nhận coordinate-space `raw_pdf_raster_pixels` và
`transform_to_source=identity` khỏi compatibility route `src/pdf_layout_web.py`.
Route vẫn giữ vai trò đọc file và dựng dữ liệu cho viewer; policy về layout
được sở hữu bởi `saxophone.extraction.layout`.

## Thay đổi

- Thêm `is_raw_pdf_raster_space()` trong extraction layout module.
- Export helper qua facade `saxophone.extraction`.
- Route dùng helper và không còn tự đọc các field coordinate-space.
- Bổ sung test cho metadata hợp lệ, transform không hỗ trợ và payload không
  phải mapping.

## Bằng chứng kiểm tra

- `uv run pytest tests/test_extraction_layout_normalization.py tests/test_phase_7_dependency_enforcement.py -q`
  — **35 passed**.
- `git diff --check` — đạt; chỉ có cảnh báo chuẩn hóa LF/CRLF của Git trên
  Windows.

## Giới hạn còn lại

Execution legacy trong `_run_extraction()` vẫn là compatibility path có chủ ý;
iteration này chỉ di chuyển policy coordinate-space thuần, không thay đổi
runtime OCR/Paddle.
