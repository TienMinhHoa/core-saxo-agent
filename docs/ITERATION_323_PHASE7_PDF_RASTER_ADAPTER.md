# Iteration 323 — tách adapter raster PDF khỏi HTTP interface

## Phạm vi

Tiêu chí Phase 7 yêu cầu `pdf_layout_web.py` không còn chứa business/orchestration
logic. Slice này tách riêng bước raster hóa trang PDF bằng Poppler; không thay đổi
API, state contract hay pipeline OCR.

## Thay đổi

- Tạo `saxophone.extraction.pdf_pages.render_pdf_pages()` làm adapter cục bộ cho
  `pdftoppm`, gồm kiểm tra dependency, tạo thư mục output và sắp xếp trang theo số.
- Workflow mới dùng adapter qua public extraction facade thay vì route tự cung cấp
  callback raster hóa.
- Thêm unit test cho câu lệnh Poppler, thứ tự trang số học và lỗi thiếu dependency.

## Bằng chứng

- Targeted: `uv run pytest -q tests/test_pdf_pages.py tests/test_phase_7_pdf_layout_wrapper.py`
- Targeted suite đạt; full suite sau khi cập nhật exact-set facade contract cần chạy lại.
- Live model-service smoke/production parity vẫn chưa xác minh vì checkout thiếu
  endpoint, credential và production catalog thật.
