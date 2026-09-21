# Iteration 230 — an toàn khi đọc Chroma sidecar

## Phạm vi

Iteration này xử lý một đơn vị nhỏ còn thiếu trong yêu cầu file-safety của
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: `ChromaChunkService.asset_path()`
đọc `chunk-records.json` nhưng trước đây chưa kiểm tra symbolic link. Vì vậy,
sidecar có thể bị chuyển hướng sang một file hoặc thư mục ngoài
`persist_dir` trước khi parse JSON.

## Thay đổi

- Thêm `_validate_sidecar_path()` để kiểm tra từng component của absolute path
  trước khi gọi `read_text()`.
- Nếu sidecar hoặc bất kỳ parent component nào là symbolic link, service
  fail-closed bằng `NotFound("chroma_sidecar_missing")`; không đọc dữ liệu đã
  bị chuyển hướng.
- Bổ sung contract tests cho parent symlink, file symlink và tình huống mô
  phỏng sidecar đổi thành symlink trước khi đọc.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_chroma_service_sidecar_safety.py -q`: **1 passed,
  2 skipped**. Hai test filesystem thật được skip có kiểm soát vì Windows
  account hiện tại không có quyền tạo symbolic link (WinError 1314); test mô
  phỏng vẫn chạy và xác minh fail-closed.
- `uv run pytest --basetemp=.pytest-tmp -q`: **916 passed, 17 skipped, 1
  warning**.
- `python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.

## Trạng thái còn lại

Production golden parity và live model-service smoke chưa thể xác minh trong
checkout này vì chưa có endpoint, credential và production catalog thật.
