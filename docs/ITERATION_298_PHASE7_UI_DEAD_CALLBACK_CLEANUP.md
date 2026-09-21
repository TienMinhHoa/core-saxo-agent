# Iteration 298 - Dọn dead code callback UI Phase 7

## Phạm vi

Tiếp tục tách root entrypoint theo hướng Clean Code trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Slice này chỉ xử lý phần thân không
thể chạy sau `return` trong hai callback Gradio `ask_chroma` và `ask_answer`.

## Thay đổi

- Rút gọn hai callback trong `app.py` thành các adapter mỏng gọi
  `music_rag.ui_workflows.handle_chroma_request()` và
  `music_rag.ui_workflows.handle_answer_request()`.
- Xóa logic retrieval, chọn record, gọi answer agent và xử lý lỗi đã trở thành
  dead code sau khi facade được wiring.
- Xóa các import legacy không còn được root entrypoint sử dụng; giữ lại
  compatibility facade cho asset/rendering.
- Bổ sung AST contract test yêu cầu mỗi callback chỉ có đúng một `return`, đồng
  thời bảo đảm root không tự chọn record hoặc giữ import typing cũ.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_7_legacy_ui_boundary.py tests/test_phase_7_ui_workflow_policy.py tests/test_app.py -q` -> **16 passed, 1 skipped**; test Gradio bị skip vì môi trường không cài Gradio.
- Syntax: `uv run python -m compileall -q app.py src tests` -> đạt.
- Hygiene: `git diff --check` -> đạt; Git chỉ cảnh báo chuyển LF/CRLF.

## Còn lại

Live model-service smoke và production golden parity vẫn chưa xác minh được vì
checkout không có endpoint, credential và production catalog thật.
