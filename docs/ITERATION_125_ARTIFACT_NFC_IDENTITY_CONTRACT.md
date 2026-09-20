# Iteration 125 - Canonical Unicode cho artifact identity

## Phạm vi

Iteration này tiếp tục hardening contract `ArtifactRef` trong Phase 2 của
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. `artifact_id` và `version` được
dùng để tạo identity immutable và đường dẫn storage; vì vậy cùng một chuỗi
Unicode nhìn giống nhau không được tạo ra hai identity khác nhau.

## Thay đổi

- `is_safe_artifact_reference()` từ chối identity không ở dạng Unicode NFC.
- Chính sách được dùng chung cho cả `ArtifactRef.artifact_id` và
  `ArtifactRef.version`.
- Bổ sung test cho dạng decomposed (`e` + combining acute) và test xác nhận
  dạng NFC hợp lệ vẫn được chấp nhận.

## Kiểm chứng

```text
uv run pytest tests/test_phase_2_artifact_reference_contract.py -q
uv run pytest
uv run python -m compileall -q src tests
git diff --check
```

Kết quả: targeted **41 passed**; full suite **547 passed, 3 skipped, 1
warning**; `compileall` và `git diff --check` đều thành công.
Đây là kiểm chứng offline; live model-service smoke và production golden
parity vẫn chưa thể chạy vì checkout chưa có endpoint, credential và catalog
production được phê duyệt.
