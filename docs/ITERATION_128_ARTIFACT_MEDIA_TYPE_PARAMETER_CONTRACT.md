# Iteration 128 — Contract parameter MIME của ArtifactRef

## Phạm vi

Tiếp tục Phase 2 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: siết metadata
`ArtifactRef` trước khi artifact được lưu hoặc truyền qua boundary. Iteration này
chỉ xử lý cú pháp parameter MIME; không thay đổi storage adapter hay pipeline.

## Thay đổi

- `is_safe_media_type()` yêu cầu mỗi parameter có tên token và giá trị token hoặc
  quoted-string hợp lệ.
- Từ chối parameter rỗng, thiếu tên, thiếu giá trị, hoặc quoted-string có quote
  không được escape.
- Giữ tương thích với MIME chuẩn dạng `application/json; charset=utf-8` và
  quoted value dạng `charset="utf-8"`.
- Bổ sung contract tests cho các trường hợp invalid/valid nêu trên.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_2_artifact_reference_contract.py tests/test_phase_2_artifact_storage_contract.py -q
74 passed, 1 skipped

uv run pytest -q
560 passed, 3 skipped, 1 warning

uv run python -m compileall -q src tests
git diff --check
```

Skip còn lại là test symbolic link trên Windows do thiếu quyền tạo symlink;
đây là giới hạn môi trường, không phải test failure. Warning đến từ alias
deprecated của Starlette/AnyIO trong dependency.

## Trạng thái và giới hạn

Contract offline đã xanh. Live model-service smoke và production golden parity
chưa thể xác minh trong checkout này vì vẫn thiếu endpoint, credential và
catalog production được phê duyệt.
