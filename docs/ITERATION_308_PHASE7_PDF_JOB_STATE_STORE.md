# Iteration 308 - tách policy lưu state PDF job

## Mục tiêu

Tiếp tục Phase 7 trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: giảm business/persistence logic trong HTTP interface `pdf_layout_web.py` mà không thay đổi contract API hiện có.

## Thay đổi

- Thêm `PdfLayoutJobStore` tại `src/saxophone/workflows/pdf_layout_jobs.py`.
- Store sở hữu validation UUID, đọc JSON state, ghi state bằng file tạm rồi `replace`, và projection các trường an toàn cho browser.
- Interface PDF dùng store cho job directory và state I/O; public facade `saxophone.workflows.__all__` vẫn giữ exact-set cũ.
- Thêm contract tests cho round-trip, identifier không hợp lệ, và loại bỏ field nội bộ khỏi public state.

## Bằng chứng kiểm chứng

- Targeted: `uv run pytest -q tests/test_pdf_layout_job_store.py tests/test_phase_7_pdf_layout_wrapper.py tests/test_phase_7_dependency_enforcement.py` -> **54 passed**.
- Full suite: `uv run pytest -q` -> **997 passed, 18 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` -> đạt.
- `git diff --check` -> đạt.

## Trạng thái còn lại

Slice này chỉ xác minh offline. Live model-service smoke và production parity vẫn chưa thể chạy vì checkout chưa có endpoint, credential và production catalog thật.
