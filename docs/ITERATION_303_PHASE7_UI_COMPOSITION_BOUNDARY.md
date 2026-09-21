# Iteration 303 — ranh giới composition của legacy UI

## Mục tiêu

Giảm business logic ở root `app.py` theo Phase 7 của
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, nhưng vẫn giữ compatibility
entrypoint `python app.py` và API import `from app import create_app`.

## Thay đổi

- Di chuyển Gradio composition và CLI legacy vào `src/music_rag/ui_app.py`.
- Giữ `app.py` là wrapper mỏng, chỉ re-export `create_app` và `main`.
- Chuyển assertion AST của UI boundary sang module implementation mới và
  thêm contract khẳng định root không còn function definition hay import
  provider/UI trực tiếp.

## Bằng chứng kiểm chứng

- `uv run pytest tests/test_phase_7_legacy_ui_boundary.py tests/test_app.py
  --basetemp=.pytest-tmp-303`: **10 passed, 1 skipped**.
- `uv run python -m compileall -q app.py src`: đạt.
- `git diff --check`: đạt; chỉ có cảnh báo chuẩn hóa LF/CRLF của Git trên
  Windows.
- Full suite `uv run pytest -q --basetemp=.pytest-tmp-303-full`: **987 passed,
  18 skipped, 1 warning** trong 41,03 giây.

## Trạng thái còn lại

Đây là kiểm chứng offline. Live model-service smoke và production golden parity
chưa thể xác minh vì checkout chưa có endpoint, credential và catalog production.
