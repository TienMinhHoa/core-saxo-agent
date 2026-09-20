# Iteration 120 - An toàn symbolic link của artifact

## Phạm vi

Tiếp tục contract artifact immutable ở Phase 2. `LocalArtifactRepository` không
được coi symbolic link là artifact backend-owned hợp lệ, kể cả khi link trỏ vào
một file nằm trong artifact root.

## Thay đổi

- Giữ path logic để nhận diện symlink, đồng thời dùng path đã resolve riêng cho
  containment check.
- `get()` và `put()` fail-closed với `FileExistsError` khi identity đích là
  symbolic link.
- Bổ sung regression test cho guard và test integration nếu Windows cấp quyền
  tạo symbolic link.

## Bằng chứng

- `uv run pytest tests/test_phase_2_artifact_storage_contract.py -q` -> **19
  passed, 1 skipped**. Test integration bị skip vì Windows trả `WinError 1314`
  (thiếu privilege tạo symbolic link); test mô phỏng guard vẫn chạy.
- `uv run pytest -q` -> **533 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` -> đạt.
- `git diff --check` -> đạt; chỉ còn cảnh báo chuẩn hóa LF/CRLF của Git.

## Kết luận

Artifact identity không còn bị dereference qua symbolic link ở boundary local
storage. Behavior missing artifact, directory collision, checksum và immutable
no-clobber vẫn được giữ nguyên.
