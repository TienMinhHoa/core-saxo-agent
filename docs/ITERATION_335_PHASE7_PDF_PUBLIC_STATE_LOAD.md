# Iteration 335 - boundary đọc state public của PDF job

## Phạm vi

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` bằng một slice nhỏ:
đưa thao tác đọc state rồi chiếu sang DTO an toàn cho browser vào
`PdfLayoutJobStore`, thay vì để route tự ghép `load_state()` với
`public_state()`.

## Thay đổi

- Thêm `PdfLayoutJobStore.load_public_state(job_id)`, tái sử dụng cùng policy
  `_PUBLIC_FIELDS` và cùng lỗi `PdfLayoutJobNotFound` của store.
- Route `GET /api/jobs/{job_id}` chỉ gọi facade mới và vẫn map job không tồn tại
  thành HTTP 404 ở presentation boundary.
- Bổ sung contract test chứng minh state private không lọt vào projection.

## Bằng chứng

- `uv run pytest tests/test_pdf_layout_job_store.py tests/test_phase_7_pdf_layout_wrapper.py -q`
  đạt **64 passed**.
- `uv run pytest -q` đạt **1051 passed, 18 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` đạt.
- `git diff --check` đạt.

## Giới hạn còn lại

Đây là kiểm thử offline. Live model-service smoke và production parity chưa thể
xác minh vì checkout chưa có endpoint, credential và production catalog được phê
duyệt.
