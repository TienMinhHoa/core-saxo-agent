# Iteration 123 - Contract MIME type của artifact

## Phạm vi

Iteration này siết một điểm nhỏ của Phase 2 trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: `ArtifactRef` phải chặn
`media_type` không có cấu trúc MIME type hợp lệ trước khi repository hoặc API
đọc và phục vụ artifact.

## Thay đổi

- Thêm policy thuần `is_safe_media_type()` yêu cầu đúng dạng `type/subtype`.
- Cho phép MIME parameter hợp lệ, ví dụ `application/json; charset=utf-8`.
- `ArtifactRef` fail-closed với thiếu subtype, nhiều dấu `/`, khoảng trắng sai
  vị trí và giá trị không phải chuỗi.
- Bổ sung regression tests cho các trường hợp invalid và MIME parameter.

## Kiểm chứng

```text
uv run pytest tests/test_phase_2_artifact_reference_contract.py
```

Kết quả: đạt.

```text
uv run pytest
uv run python -m compileall -q src tests
git diff --check
```

Kết quả: `539 passed, 3 skipped, 1 warning`; compileall đạt; `git diff --check`
đạt. Một test symbolic-link được skip do Windows checkout không có quyền tạo
symbolic link.

Các kiểm chứng trên là offline. Live model-service smoke và production golden
parity vẫn chưa chạy vì checkout chưa có endpoint, credential và catalog
production được cấp phép.
