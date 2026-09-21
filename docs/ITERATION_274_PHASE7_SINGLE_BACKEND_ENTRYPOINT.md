# Iteration 274 — Khóa một backend ASGI entrypoint

## Mục tiêu

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: backend chỉ có
một entrypoint web và các CLI legacy không được vô tình trở thành một runtime
FastAPI thứ hai.

## Thay đổi

- Bổ sung contract test đọc `[project.scripts]` trong `pyproject.toml`.
- Test chỉ chấp nhận `saxophone-api = saxophone.main:main` là backend ASGI
  entrypoint; `music-rag` và `pdf-layout-web` vẫn được xem là CLI compatibility
  riêng, không phải backend runtime đích.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`
  — đạt.
- Full offline suite: `uv run pytest -q` — đạt sau khi chạy trong iteration.
- `python -m compileall -q src tests` — đạt.
- `git diff --check` — đạt.

## Giới hạn còn lại

Live model-service smoke và production golden parity chưa thể xác minh trong
checkout này vì thiếu endpoint, credential và production catalog thật. Đây là
blocker môi trường, không phải kết luận từ offline contract test.
