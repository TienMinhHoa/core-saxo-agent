# Iteration 124 - Contract control character trong artifact identity

## Phạm vi

Iteration này tiếp tục Phase 2 của
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: `ArtifactRef` phải giữ identity
ổn định, an toàn trước khi adapter ánh xạ sang filesystem. Các iteration trước
đã chặn traversal, path component dạng symbolic link, ghi đè immutable artifact
và MIME type thiếu cấu trúc.

## Thay đổi

- Siết `is_safe_artifact_reference()` theo hướng fail-closed với mọi control
  character ASCII (U+0000–U+001F và U+007F), bao gồm newline, tab và DEL.
- Áp dụng chung cho cả `artifact_id` và `version`, tránh identity làm hỏng log,
  tên file hoặc boundary giữa các dòng khi đi qua storage adapter.
- Bổ sung regression tests cho newline, tab và DEL ở cả hai trường.

## Kiểm chứng

```text
uv run pytest tests/test_phase_2_artifact_reference_contract.py
uv run pytest
uv run python -m compileall -q src tests
git diff --check
```

Kết quả iteration: targeted contract pass; full suite pass; compileall và
`git diff --check` pass.

Các kiểm chứng này là offline. Live model-service smoke và production golden
parity vẫn chưa thể chạy vì checkout chưa có endpoint, credential và catalog
production được cấp phép.
