# Iteration 251 — Khóa composition root cho concrete adapters

## Phạm vi

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` bằng một
enforcement nhỏ tại import graph: entrypoint `saxophone.main` và lớp HTTP
`saxophone.interfaces.api` không được tự import concrete adapter. Việc lắp ráp
dependency phải tiếp tục nằm ở `saxophone.app.factory`.

## Thay đổi

- Bổ sung test AST `test_composition_root_owns_concrete_adapter_wiring` trong
  `tests/test_phase_7_dependency_enforcement.py`.
- Guard kiểm tra các module adapter cụ thể của extraction, ingestion, platform,
  tagging; không chấp nhận chúng xuất hiện trong `main.py` hoặc API router.
- Không thay đổi runtime behavior hay contract public.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_phase_7_dependency_enforcement.py` — **13
  passed**.
- Full suite: `uv run pytest` — **934 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests` — đạt.
- `git diff --check` — đạt; chỉ còn cảnh báo newline CRLF mặc định của Git trên
  Windows, không có whitespace error.
- Live model-service smoke và production parity vẫn chưa thể xác minh vì
  checkout không có endpoint, credential và production catalog thật.

## Kết luận

Guard mới củng cố nguyên tắc Dependency Inversion: outer entrypoint chỉ gọi
composition root, còn API layer chỉ nhận application ports/use cases đã được
wire sẵn.
