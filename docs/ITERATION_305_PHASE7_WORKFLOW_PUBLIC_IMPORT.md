# Iteration 305 - Khóa import workflow PDF qua public API

## Mục tiêu

Tiếp tục Phase 7 theo `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: interface PDF
không nên phụ thuộc trực tiếp vào module triển khai workflow.

## Thay đổi

- Export `run_extraction` ở namespace `saxophone.workflows` để adapter HTTP dùng
  boundary package ổn định.
- Đổi `saxophone.interfaces.pdf_layout_web` sang
  `from saxophone.workflows import run_extraction`.
- Bổ sung contract test để ngăn import trực tiếp từ
  `saxophone.workflows.pdf_layout_extraction`; giữ nguyên `workflows.__all__`
  dành cho các application workflow công khai hiện có.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py tests/test_phase_7_dependency_enforcement.py::test_workflows_exposes_a_public_application_facade --basetemp=.pytest-tmp` -> **5 passed**.
- Full offline: `uv run pytest -q --basetemp=.pytest-tmp` -> **989 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests` -> đạt.
- `git diff --check` -> đạt; Git chỉ cảnh báo chuyển LF/CRLF trên Windows.
- Live model-service smoke và production golden parity chưa xác minh vì checkout
  vẫn thiếu endpoint, credential và production catalog thật.
