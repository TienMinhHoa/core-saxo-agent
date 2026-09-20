# Iteration 10 - guard source contract workflow direct

## Mục tiêu

Khóa một kiểm tra kiến trúc ở cấp source để ngăn contract workflow job lifecycle
cũ quay lại package backend. Kiểm tra này không quét `__pycache__` hoặc bytecode
đã sinh từ các lần chạy trước.

## Thay đổi

- Bổ sung test `test_backend_source_does_not_reintroduce_removed_job_lifecycle_contract`.
- Các tên bị cấm gồm `WorkflowJob`, `JobStatus`, `remote_job_id`,
  `JobRepository`, `JobExecutor` và các thao tác submit/poll của gateway.
- Guard chỉ đọc các file `*.py` trong `src/saxophone`, nên bằng chứng phản ánh
  source hiện hành thay vì cache cục bộ.

## Bằng chứng kiểm tra

```text
uv run pytest -q tests/test_phase_7_dependency_enforcement.py --basetemp=.pytest-tmp
4 passed

uv run pytest -q --basetemp=.pytest-tmp
285 passed, 2 skipped, 1 warning

uv run python -m compileall -q src tests
git diff --check
```

Live model-service smoke
vẫn chưa thể xác minh vì checkout chưa có endpoint và credential thật; guard này
chỉ xác minh invariant offline.
