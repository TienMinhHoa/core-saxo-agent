# Bằng chứng Iteration 116: dọn file tạm khi publish artifact thất bại

## Phạm vi

Iteration này củng cố invariant của `LocalArtifactRepository` sau commit
immutable/no-clobber ở iteration 115: nếu bước publish bằng hard-link thất bại,
repository không được để lại file tạm hoặc file artifact chưa được publish.

## Thay đổi

- Bổ sung test contract `test_atomic_commit_cleans_temporary_file_when_publish_fails`.
- Test mô phỏng `os.link` ném `OSError`, xác nhận lỗi được trả về cho caller.
- Test xác nhận không còn `*.tmp` và không có file artifact nào được tạo dở.
- Không xóa thư mục cha rỗng; đây là cấu trúc tạm đã tạo trong lúc ghi và không
  ảnh hưởng đến tính toàn vẹn artifact.

## Kiểm chứng

```text
uv run pytest tests/test_phase_2_artifact_storage_contract.py -q
15 passed

uv run pytest -q
529 passed, 2 skipped, 1 warning

uv run python -m compileall -q src tests
PASS

git diff --check
PASS
```

## Giới hạn còn lại

Đây là kiểm chứng offline. Live model-service smoke và production golden parity
vẫn chưa thể xác nhận vì checkout chưa có endpoint, credential và catalog
production thực tế.
