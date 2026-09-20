# Iteration 111 — siết kiểu runtime của ArtifactRef

## Phạm vi

`ArtifactRef` là contract domain đi vào `ArtifactRepository`. Type hint không
tự bảo vệ dữ liệu khi object được tạo từ boundary động, vì vậy identity phải
fail-closed trước khi adapter thực hiện filesystem I/O.

## Thay đổi

- `ArtifactRef` từ chối `kind` là chuỗi thường thay vì `ArtifactKind`.
- `size_bytes` phải là `int` thực sự; `bool` và số thực bị từ chối, tránh việc
  phép so sánh hoặc metadata kích thước có semantics không mong muốn.
- `media_type` tiếp tục được kiểm tra non-blank và phải là chuỗi qua helper
  domain hiện hữu.
- Bổ sung regression tests cho các giá trị sai và giữ nguyên contract immutable,
  checksum, path-safety của các iteration trước.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_2_artifact_reference_contract.py
  tests/test_phase_2_artifact_storage_contract.py`: **34 passed**.
- Kiểm thử chứng minh dữ liệu sai bị chặn ở domain boundary, trước khi
  `LocalArtifactRepository` thực hiện I/O.

## Trạng thái

Đạt offline cho contract runtime type của artifact identity. Live model-service
smoke và production golden parity vẫn chưa xác minh vì checkout chưa có
endpoint, credential và catalog production thật.
