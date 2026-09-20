# Iteration 101 — Chuẩn hóa image reference và chặn path tương đương

## Phạm vi

Tiếp tục yêu cầu file safety trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
image reference phải là đường dẫn tương đối, thuộc namespace backend và có một
cách viết canonical duy nhất.

## Thay đổi

- `SafeImageArtifactGate` từ chối `images//page-1.png` và
  `images/./page-1.png`.
- Vẫn giữ các guard hiện có cho URL/host, absolute path, backslash, khoảng
  trắng và `..` traversal.
- Quy tắc canonical dùng `Path.as_posix()` sau khi đã loại các segment nguy
  hiểm; vì vậy không thay đổi giao diện artifact hay đưa filesystem path vào
  application contract.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_chat_answer_question.py -k safe_image_artifact_gate -q
2 passed, 11 deselected

uv run pytest tests/test_phase_2_artifact_storage_contract.py -q
7 passed

uv run python -m compileall -q src tests
git diff --check
```

Đây là bằng chứng offline/contract trong checkout hiện tại; chưa phải live
model-service smoke hoặc production deployment evidence.
