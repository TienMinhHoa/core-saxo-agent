# Iteration 304 - Tách workflow extraction khỏi interface PDF layout

## Mục tiêu

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: file
`saxophone.interfaces.pdf_layout_web` chỉ giữ trách nhiệm HTTP boundary, không
chứa orchestration của OCR/layout extraction.

## Thay đổi

- Tạo `saxophone.workflows.pdf_layout_extraction.run_extraction()` để sở hữu
  state transition, gọi legacy OCR adapter, báo cáo tiến độ, render trang và
  ghi trạng thái thành công/thất bại.
- Route `POST /api/jobs/{job_id}/extract` chỉ khởi động workflow qua dependency
  callbacks; không còn import động legacy OCR runtime, `traceback` hoặc định
  nghĩa `_run_extraction` trong interface.
- Thêm AST contract test để ngăn orchestration quay lại file interface.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py -q` -> **3
  passed**.
- Full offline: `uv run pytest -q` -> **988 passed, 18 skipped, 1 warning**.
- `uv run python -m compileall -q src tests app.py` -> đạt.
- `git diff --check` -> đạt; chỉ còn cảnh báo chuẩn LF/CRLF của Git trên
  Windows.
- Live model-service smoke và production golden parity chưa xác minh vì
  checkout vẫn không có endpoint, credential và production catalog thật.

