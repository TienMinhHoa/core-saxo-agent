# Iteration 229 - File safety cho Chroma sidecar JSON

## Phạm vi

Theo mục **20. Security và file safety** trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, sidecar JSON được ghi trong quá
trình indexing phải fail-closed nếu bất kỳ thành phần nào của đường dẫn có thể
bị chuyển hướng qua symbolic link.

## Thay đổi

- `_write_json()` kiểm tra đường dẫn trước và sau khi tạo thư mục cha.
- `_write_json()` kiểm tra lại đường dẫn sau khi flush temporary file và trước
  `os.replace()`, nên không publish nếu đường dẫn đã đổi trong lúc ghi.
- Bổ sung contract tests cho symbolic-link parent, symbolic-link target và
  race path trước replace.

## Bằng chứng

- Targeted: `uv run pytest tests/test_chroma_sidecar_safety.py
  tests/test_chroma_sidecar_contract.py` đạt **2 passed, 2 skipped**. Hai test
  symbolic-link được skip vì Windows account hiện tại không có quyền tạo
  symbolic link (WinError 1314).
- Full offline suite: **915 passed, 15 skipped, 1 warning**.
- `python -m compileall -q src tests` và `git diff --check` đạt.

## Ngoài phạm vi

Không thay đổi schema Chroma, metadata projection, embedding provider hoặc
retrieval behavior.

