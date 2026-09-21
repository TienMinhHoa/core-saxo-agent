# Iteration 269 - boundary hằng số layout PDF

## Mục tiêu

Hoàn tất một phần nhỏ của Phase 7: route tương thích `src/pdf_layout_web.py`
không được phụ thuộc trực tiếp vào module layout legacy `extracted`.

## Thay đổi

- Chuyển import `RAW_PDF_RASTER_SPACE` của route sang
  `saxophone.extraction.layout`, nơi đã sở hữu logic chuẩn hóa layout.
- Bổ sung contract test AST để ngăn route tái nhập
  `extracted.layout_geometry`.
- Giữ nguyên compatibility wrapper và hành vi hiển thị hiện tại; không di
  chuyển pipeline OCR/GPU trong slice này.

## Bằng chứng xác minh

- TDD targeted: trước khi sửa, contract test thất bại vì route còn import
  `extracted.layout_geometry`; sau khi sửa, test đạt `1 passed`.
- Full suite đạt `955 passed, 18 skipped, 1 warning`.
- `python -m compileall -q src tests` đạt.
- `git diff --check` đạt; chỉ còn cảnh báo chuẩn hóa LF/CRLF của Git trên
  Windows.

## Phạm vi chưa kết luận

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout hiện không có endpoint, credential và catalog production thật.
