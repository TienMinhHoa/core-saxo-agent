# Iteration 109 - An toàn version của artifact

## Phạm vi

`LocalArtifactRepository` ánh xạ artifact theo cấu trúc `artifact_id/version`.
Iteration 108 đã khóa `artifact_id`, nhưng `ArtifactRef.version` mới chỉ kiểm tra
không-blank. Vì vậy một version như `../outside`, đường dẫn tuyệt đối hoặc đường
dẫn Windows vẫn có thể đi vào phép ghép path ở storage adapter.

## Thay đổi

- `ArtifactRef` dùng cùng policy relative-reference cho `version`.
- Từ chối traversal (`..`), segment rỗng hoặc `.`, absolute path, backslash,
  drive separator và các dạng không canonical ngay tại domain boundary.
- Mở rộng contract test để kiểm tra cả `artifact_id` và `version`, trước khi
  filesystem I/O xảy ra.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_2_artifact_reference_contract.py tests/test_phase_2_artifact_storage_contract.py -q
27 passed

uv run pytest -q
513 passed, 2 skipped, 1 warning

uv run python -m compileall -q src tests
git diff --check
```

`compileall` và `git diff --check` hoàn tất không có lỗi. Hai test bị skip là
phụ thuộc Gradio và sample source, không liên quan thay đổi này.

## Trạng thái còn lại

Live model-service smoke và production golden parity chưa thể xác minh vì
checkout chưa có endpoint, credential và catalog production thật.
