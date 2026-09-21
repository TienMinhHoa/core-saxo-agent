# Iteration 286 - Dọn dẹp UI policy khỏi root entrypoint

## Phạm vi

Refactor nhỏ theo Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: root entrypoint `app.py` chỉ lắp ráp ứng dụng và gọi facade công khai `music_rag.ui_rendering`; không giữ bản sao của các helper render/status/asset policy.

## Thay đổi

- Xóa các implementation trùng lặp trong `app.py`: status text, render source bundle, kiểm tra đường dẫn ảnh Chroma, allow-list asset và render kết quả Chroma.
- Giữ các tên tương thích bằng import alias từ `music_rag.ui_rendering`, nên call site hiện tại không đổi.
- Thêm AST contract test để ngăn `app.py` định nghĩa lại các UI policy helper.

## Bằng chứng kiểm thử

- Targeted boundary tests: `3 passed` với `uv run pytest tests/test_phase_7_legacy_ui_boundary.py`.
- Full offline suite: `969 passed, 18 skipped, 1 warning` với `uv run pytest`.
- Syntax: `uv run python -m compileall -q app.py src tests`.
- Diff hygiene: `git diff --check` không báo lỗi.

Live model-service smoke và production golden parity vẫn chưa thể xác minh trong checkout này vì thiếu endpoint, credential và catalog production được phê duyệt.
