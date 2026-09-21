# Iteration 338 — Ranh giới khởi chạy extraction PDF

## Mục tiêu

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: HTTP interface
không tự biết cách tạo worker thread cho extraction; việc khởi chạy workflow phải
được sở hữu bởi public workflow facade.

## Thay đổi

- Thêm `start_extraction()` vào `saxophone.workflows`, nhận typed artifact path
  policy và các dependency I/O qua injection.
- Workflow tạo daemon worker, cấu hình `run_extraction()` và gọi `start()`;
  route `POST /api/jobs/{job_id}/extract` chỉ queue state rồi ủy quyền launch.
- Loại bỏ chi tiết `threading.Thread` và `.start()` khỏi HTTP interface; route
  vẫn giữ nguyên response/error contract.
- Cập nhật contract tests để bảo vệ public export, wiring dependency và daemon
  worker policy.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py -q` — **36 passed**.
- Full offline: `uv run pytest -q` — **1059 passed, 18 skipped, 1 warning**.
- Syntax: `uv run python -m compileall -q src tests`.
- Live model-service smoke và production parity chưa chạy vì checkout vẫn thiếu
  endpoint, credential và production catalog được phê duyệt.

## Trạng thái

Slice này hoàn tất một boundary cleanup độc lập. Stop condition toàn bộ kiến
trúc chưa đạt vì các exit criteria/live smoke còn lại cần được kiểm tra riêng.
