# Iteration 302 — Chuẩn hóa import helper UI ở root entrypoint

## Phạm vi

Theo Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, root `app.py` chỉ
nên làm nhiệm vụ bootstrap và wiring giao diện. Slice này xử lý phần alias
private còn sót lại khi import các helper render thuần.

## Thay đổi

- `app.py` import trực tiếp các public helper `format_answer_cost` và
  `render_chroma_results` từ `music_rag.ui_rendering`.
- Callback Gradio truyền trực tiếp các helper public vào workflow facade;
  behavior và contract trả về không đổi.
- Thêm AST contract test để ngăn alias private `_format_answer_cost` và
  `_render_chroma_results` quay lại root entrypoint.

## Bằng chứng kiểm chứng

- `uv run pytest -q tests/test_phase_7_legacy_ui_boundary.py tests/test_app.py`
  → **9 passed, 1 skipped**; test Gradio bị skip vì dependency không có trong
  môi trường offline.
- Không chạy live model-service smoke trong iteration này vì checkout vẫn
  không có endpoint, credential và production catalog cần thiết.

## Kết luận

Slice import boundary của Phase 7 đã được khóa bằng test source-level; không có
thay đổi runtime ngoài việc bỏ alias private không cần thiết.
