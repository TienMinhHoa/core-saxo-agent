# Iteration 291 — dùng trực tiếp policy số của extraction trong PDF route

## Phạm vi

Lát cắt này tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.
Mục tiêu là loại bỏ một compatibility wrapper không cần thiết trong route PDF:
`_number()` chỉ chuyển tiếp tới policy `finite_number()` đã thuộc facade
`saxophone.extraction`.

## Thay đổi

- Xóa `_number()` khỏi `saxophone.interfaces.pdf_layout_web`.
- `_layout_pages()` gọi trực tiếp `finite_number()` cho chiều rộng và chiều cao.
- Thêm contract test để ngăn wrapper quay lại và giữ dependency qua facade.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py -q`
  — **2 passed**.
- Full offline suite: `uv run pytest -q` — **971 passed, 18 skipped, 1 warning**
  trong **40.95 giây**.
- `python -m compileall -q app.py src tests` — đạt.
- `git diff --check` — đạt; chỉ có cảnh báo chuyển đổi LF/CRLF của Git trên
  Windows.

Các test bị skip vẫn là các trường hợp môi trường không có Gradio, không có
sample source, hoặc tài khoản Windows không được tạo symbolic link. Live
model-service smoke và production golden parity tiếp tục chưa xác minh vì
checkout không có endpoint, credential và catalog production được phê duyệt.
