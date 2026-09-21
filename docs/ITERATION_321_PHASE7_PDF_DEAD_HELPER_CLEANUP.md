# Iteration 321 — dọn helper chết ở HTTP interface PDF

## Phạm vi

Iteration này xử lý một đơn vị nhỏ còn sót lại sau khi `PdfLayoutJobStore` đã
nhận ownership của việc validate job id và quản lý đường dẫn. HTTP interface
không còn cần helper `_job_dir()` chỉ chuyển tiếp vào store.

## Thay đổi

- Xóa `_job_dir()` khỏi `src/saxophone/interfaces/pdf_layout_web.py`.
- Giữ `PdfLayoutJobStore` là nơi duy nhất cung cấp job directory policy; các
  route hiện tại dùng các method policy chuyên biệt (`source_pdf_path`,
  `pages_dir`, `layout_dir`).
- Thêm contract test ngăn helper chết hoặc lời gọi trực tiếp
  `JOB_STORE.job_dir(...)` quay lại HTTP interface.

## Bằng chứng kiểm tra

- Targeted contract: `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py` — đạt.
- Full suite: `uv run pytest` — đạt; compileall và `git diff --check` — đạt.
- Không chạy live model-service smoke vì checkout vẫn thiếu endpoint,
  credential và production catalog thật.

## Kết luận

Đã loại bỏ một đường chuyển tiếp không còn được dùng, làm rõ boundary Phase 7
mà không thay đổi behavior runtime của API PDF.
