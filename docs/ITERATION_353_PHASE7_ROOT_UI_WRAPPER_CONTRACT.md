# Iteration 353 - khóa contract wrapper UI legacy ở root

## Phạm vi

Lát cắt này kiểm tra exit criterion Phase 7: `app.py` ở root không chứa
business logic của UI legacy. File này chỉ được phép re-export launcher từ
`music_rag.ui_app`, để backend web chính vẫn là `saxophone-api`.

## Thay đổi

- Bổ sung contract test AST cho `app.py`.
- Test yêu cầu root entrypoint chỉ import `create_app` và `main` từ
  `music_rag.ui_app`, đồng thời không import trực tiếp Gradio hoặc Chroma.
- Không thay đổi runtime code vì wrapper hiện tại đã thỏa contract; test mới
  khóa hành vi để ngăn business logic quay lại root file.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`: **48 passed**.
- `uv run pytest -q`: **1067 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests`: **đạt**.
- `git diff --check`: **đạt** (chỉ có cảnh báo chuyển đổi LF/CRLF của Git).

Live model-service smoke và production parity chưa thể xác minh trong checkout
này vì thiếu endpoint, credential và production catalog được phê duyệt.
