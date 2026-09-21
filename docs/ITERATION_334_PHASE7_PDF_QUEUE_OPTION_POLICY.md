# Iteration 334 — policy option queue PDF thuộc `PdfLayoutJobStore`

## Phạm vi

Lát cắt này tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
HTTP interface chỉ điều phối request; policy hợp lệ của một chuyển trạng thái
queue phải nằm ở boundary sở hữu job state.

## Thay đổi

- Thêm `PdfLayoutJobRequestError` làm lỗi contract riêng cho option extraction.
- `PdfLayoutJobStore.queue_extraction()` nay tự chuẩn hóa `device` và
  `language`, sau đó kiểm tra `cpu`/`gpu:<index>` và mã ngôn ngữ ASCII dài 2–20
  ký tự trước khi đọc và ghi state.
- Route `POST /api/jobs/{job_id}/extract` không còn chứa regex hoặc policy
  normalize; route chỉ map lỗi option thành HTTP 400 và conflict state thành
  HTTP 409.
- Export lỗi contract qua `saxophone.workflows` để interface không phụ thuộc
  module triển khai.

## Bằng chứng

- `uv run pytest tests/test_pdf_layout_job_store.py tests/test_phase_7_pdf_layout_wrapper.py -q`
  → **63 passed**.
- Test bao phủ option sai, canonicalization, HTTP mapping và guard không cho
  route sở hữu lại validation policy.

## Giới hạn còn lại

Đây là kiểm thử offline. Live model-service smoke và production parity vẫn
chưa thể xác minh vì checkout chưa có endpoint, credential và catalog production
được phê duyệt.
