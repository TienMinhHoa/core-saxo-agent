# Iteration 314 - Ranh giới trạng thái queued của PDF job

## Phạm vi

Iteration này tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.
Mục tiêu nhỏ là chuyển policy chuyển một PDF job sang trạng thái `queued` ra
khỏi HTTP interface và giao cho `PdfLayoutJobStore` sở hữu cùng persistence
boundary với trạng thái ban đầu và public projection.

## Thay đổi

- Thêm `PdfLayoutJobStore.queue_extraction()` để:
  - chỉ cho phép job ở trạng thái `uploaded` hoặc `failed` được queue;
  - lưu `device`, `language`, phase/progress mặc định và xoá lỗi cũ;
  - ghi state qua atomic `write_state()`.
- Route `POST /api/jobs/{job_id}/extract` chỉ chuẩn hoá input, gọi store và
  khởi động workflow; không còn tự mutate dictionary state.
- Thêm unit test cho state transition/persistence và AST contract test bảo vệ
  route delegation.

## Bằng chứng kiểm tra

- `uv run pytest tests/test_pdf_layout_job_store.py tests/test_phase_7_pdf_layout_wrapper.py -q`
  - **22 passed**.
- Full suite, `compileall` và `git diff --check` sẽ được chạy sau slice này.
- Live model-service smoke và production parity vẫn chưa xác minh vì checkout
  chưa có endpoint, credential và production catalog thật.

## Kết luận

Slice này đạt mục tiêu ranh giới persistence cho trạng thái `queued`, không
thay đổi API response hay thêm job-status lifecycle mới.
