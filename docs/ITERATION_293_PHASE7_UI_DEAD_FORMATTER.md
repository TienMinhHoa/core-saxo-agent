# Iteration 293 — loại bỏ formatter UI chết khỏi root entrypoint

## Phạm vi

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: root
`app.py` không giữ helper trình bày đã không còn được sử dụng. Slice này chỉ
xử lý `_answer_cost_markdown`, không thay đổi luồng Gradio hoặc contract của
`music_rag.ui_rendering`.

## Thay đổi

- Thêm contract AST trong `tests/test_phase_7_legacy_ui_boundary.py` để cấm
  `_answer_cost_markdown` quay lại root entrypoint.
- Xóa `_answer_cost_markdown` và import `typing.Any` không còn cần thiết khỏi
  `app.py`.
- Formatter đang được sử dụng vẫn là `music_rag.ui_rendering.format_answer_cost`;
  không xóa implementation đang phục vụ tab Answer RAG.

## Bằng chứng kiểm thử

- TDD red trước khi sửa: `1 failed, 4 passed` vì helper chết vẫn tồn tại.
- Targeted sau khi sửa: `uv run pytest tests/test_phase_7_legacy_ui_boundary.py -q`
  đạt **5 passed**.
- Full suite: `uv run pytest -q` đạt **973 passed, 18 skipped, 1 warning**.
- `python -m compileall -q app.py src tests` đạt.
- `git diff --check` đạt; chỉ còn cảnh báo line ending CRLF tự nhiên của Git
  trên Windows.

## Trạng thái còn lại

Slice này chưa chứng minh live model-service smoke hoặc production golden
parity; checkout vẫn thiếu endpoint, credential và catalog production được
phê duyệt.
