# Iteration 122 — Bằng chứng contract artifact parent path

## Phạm vi

Iteration này chốt một đơn vị nhỏ của Phase 2 trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: filesystem adapter phải giữ
artifact immutable, không cho path component là symbolic link, và không được
ghi đè artifact đã tồn tại.

## Kết quả đã có trong codebase

- `LocalArtifactRepository._path_for()` kiểm tra từng component của
  `artifact_id/version` trước khi filesystem I/O tiếp tục.
- `put()` và `get()` đều fail-closed nếu artifact identity hoặc parent path là
  symbolic link.
- Publish dùng hard-link từ file tạm đã flush/fsync, nên không dùng
  `os.replace()` để clobber destination do writer khác vừa tạo.
- Contract tests bao phủ directory collision, missing artifact, symbolic link
  tại identity, symbolic link tại parent path, publish race, cleanup khi publish
  thất bại, và concurrent immutable writes.

## Kiểm chứng iteration

```text
uv run pytest
534 passed, 3 skipped, 1 warning

uv run python -m compileall -q src tests
Đạt

git diff --check
Đạt
```

Các kiểm chứng trên là offline. Live model-service smoke và production golden
parity chưa thể chạy vì checkout hiện không có endpoint, credential và catalog
production được cấp phép.

## Trạng thái nghiệm thu

Đơn vị contract artifact parent-path đã đạt offline. Stop condition của toàn bộ
refactor chưa đạt vì live model-service smoke và production parity vẫn là
blocker bên ngoài codebase.
