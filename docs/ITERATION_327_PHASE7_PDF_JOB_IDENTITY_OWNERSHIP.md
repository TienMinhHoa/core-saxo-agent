# Iteration 327 — Ownership identity và timestamp PDF job

## Phạm vi

Sau Iteration 326, `PdfLayoutJobStore` đã sở hữu state, artifact path, upload và
cleanup. HTTP interface vẫn tự sinh UUID và timestamp trước khi gọi store, nên
policy tạo job còn bị chia đôi.

## Thay đổi

- Đưa việc sinh UUID và timestamp UTC vào `PdfLayoutJobStore.create_uploaded_job()`.
- Giữ `job_id` và `created_at` tùy chọn để test/migration có thể truyền giá trị
  deterministic; production route chỉ truyền tên file.
- Route upload lấy `job_id` từ state do store trả về; interface không còn import
  `uuid`/`time` hoặc sở hữu helper timestamp.
- Thêm contract test cho identity/timestamp tự sinh và guard source boundary.

## Bằng chứng kiểm chứng

- `uv run pytest tests/test_pdf_layout_job_store.py tests/test_phase_7_pdf_layout_wrapper.py -q`
  — **38 passed**.
- `uv run pytest -q` — **1025 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests` — đạt.
- `git diff --check` — đạt; chỉ còn cảnh báo line ending CRLF của Git trên
  các file Python đã chỉnh sửa.
- Live model-service smoke và production parity chưa xác minh vì checkout vẫn
  thiếu endpoint, credential và production catalog.

## Kết luận

Slice này hoàn tất thêm một phần ownership của Phase 7: persistence boundary
chịu trách nhiệm trọn vẹn việc tạo identity/thời điểm job, còn HTTP interface
chỉ phối hợp request và chuyển state ra response.
