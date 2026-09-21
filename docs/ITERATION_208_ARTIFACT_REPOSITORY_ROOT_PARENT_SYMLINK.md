# Iteration 208 - chặn symbolic link trong parent path của artifact root

## Phạm vi

Iteration này tiếp tục harden `LocalArtifactRepository` theo yêu cầu safe-path
và fail-closed trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Guard trước đó
chỉ kiểm tra chính `root`; một parent component là symbolic link vẫn có thể bị
`Path.resolve()` dẫn sang thư mục ngoài root mà operator đã cấu hình.

## Thay đổi

- Constructor gọi `_reject_symbolic_link_in_path()` trước khi resolve root.
- Helper duyệt từng component của absolute path và từ chối cả root cuối lẫn
  symbolic link ở parent path.
- Bổ sung regression test mô phỏng parent symbolic link, không phụ thuộc quyền
  tạo symlink thật trên Windows.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_2_artifact_storage_contract.py --basetemp=.pytest-tmp -q`
  → **30 passed, 1 skipped**; skip là test symlink thật do Windows thiếu quyền.
- `uv run pytest --basetemp=.pytest-tmp -q`
  → **896 passed, 3 skipped, 1 warning**.
- `python -m compileall -q src tests` → đạt.
- `git diff --check` → đạt.

Live model-service smoke và production golden parity vẫn chưa xác minh vì
checkout chưa có endpoint, credential và production catalog thật.
