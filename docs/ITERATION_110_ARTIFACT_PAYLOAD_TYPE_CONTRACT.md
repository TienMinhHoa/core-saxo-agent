# Iteration 110 — hợp đồng kiểu payload artifact

## Phạm vi

Siết boundary của `ArtifactRepository.put()` theo yêu cầu artifact transfer
phải có kiểm soát rõ ràng. `ArtifactRef` đã khai báo kích thước và SHA-256;
iteration này bổ sung điều kiện payload phải là `bytes` trước mọi thao tác
filesystem.

## Thay đổi

- `LocalArtifactRepository` từ chối `str`, `bytearray` và `memoryview` bằng
  `ValueError("payload must be bytes")`.
- Validation diễn ra trước `anyio.to_thread.run_sync()`, nên input sai không
  tạo thư mục, file tạm hoặc provider/filesystem I/O.
- Quy tắc size và SHA-256 hiện hữu vẫn được giữ nguyên.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_2_artifact_storage_contract.py`: **10 passed**.
- Test mới xác minh ba kiểu không phải `bytes` đều bị reject và thư mục lưu
  vẫn rỗng.

## Trạng thái nghiệm thu

Đã hoàn thành kiểm tra offline cho boundary kiểu payload. Live model-service
smoke và production golden parity vẫn chưa xác minh vì checkout chưa có
endpoint, credential và catalog production thật.
