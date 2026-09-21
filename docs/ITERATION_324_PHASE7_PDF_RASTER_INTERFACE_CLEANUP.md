# Iteration 324 - loại bỏ raster hóa PDF khỏi HTTP interface

## Phạm vi

Tiếp tục Phase 7 của kế hoạch refactor: `saxophone.interfaces.pdf_layout_web`
không được giữ business logic hoặc triển khai adapter raster hóa PDF. Adapter
Poppler đã được tách ở iteration trước; slice này dọn phần triển khai cũ còn
sót trong route module.

## Thay đổi

- Xóa `_render_pages()` cùng các import `shutil` và `subprocess` khỏi HTTP
  interface.
- Xóa `_page_number()` vì chỉ phục vụ triển khai raster hóa cũ.
- Giữ wiring rõ ràng: workflow nhận `render_pdf_pages` từ public extraction
  facade qua composition của route.
- Thêm contract test bảo vệ việc interface không quay lại gọi `pdftoppm` hoặc
  giữ helper raster cục bộ.

## Bằng chứng kiểm tra

- `uv run pytest -q tests/test_phase_7_pdf_layout_wrapper.py -k "raster_implementation or pdf_layout_interface"`
  -> **4 passed**.
- `uv run pytest -q` -> **1020 passed, 18 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` -> thành công.
- `git diff --check` -> thành công; chỉ có cảnh báo quy đổi LF/CRLF của Git.
- Live model-service smoke/production parity vẫn chưa xác minh vì checkout
  chưa có endpoint, credential và production catalog thật.
