# Iteration 307 - Tách policy đọc layout khỏi HTTP interface

## Phạm vi

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` với một lát cắt
nhỏ: `saxophone.interfaces.pdf_layout_web` không giữ logic đọc JSON layout,
kiểm tra coordinate space hoặc chuẩn hóa block nữa. Interface chỉ dựng đường
dẫn thư mục và URL ảnh, sau đó gọi public extraction policy.

## Thay đổi

- Tạo `saxophone.extraction.layout_view.read_layout_pages()` để đọc các file
  `page-*.json`, kiểm tra số hữu hạn/kích thước dương, kiểm tra
  `raw_pdf_raster_pixels` và bỏ qua payload hỏng theo fail-closed policy.
- Export `read_layout_pages` qua `saxophone.extraction`.
- Route layout gọi policy mới và giữ nguyên URL ảnh, page number và danh sách
  block observable cho frontend.
- Cập nhật exact-set contract của extraction facade và thêm regression tests cho
  payload hợp lệ/không hợp lệ cùng boundary import.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py -q` -> **7 passed**.
- Full offline: `uv run pytest -q` -> **992 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests` -> đạt.
- Không chạy live model-service smoke hoặc production parity vì checkout vẫn
  thiếu endpoint, credential và production catalog thật.
