# Iteration 118 — Artifact read fail-closed khi đích là thư mục

## Phạm vi

Tiếp tục contract của `LocalArtifactRepository`: cùng một artifact identity
không được bị hiểu nhầm là payload khi filesystem object tại đích là thư mục.
Iteration 117 đã khóa đường `put()`; iteration này khóa đường `get()`.

## Thay đổi

- `LocalArtifactRepository.get()` đọc qua helper blocking I/O có kiểm tra
  `Path.is_file()` trước khi mở bytes.
- Nếu đích là thư mục (hoặc không phải file), repository trả
  `FileExistsError("artifact identity is not a file")` và không cố đọc payload.
- Bổ sung regression test tạo directory tại đúng artifact identity và xác minh
  `get()` fail-closed.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_2_artifact_storage_contract.py tests/test_phase_6_image_artifact_repository_gate.py -q
20 passed
```

Đây là kiểm thử offline trên filesystem tạm. Chưa có live model-service,
production storage hoặc deployment smoke trong iteration này.

## Liên hệ yêu cầu kiến trúc

Kết quả củng cố yêu cầu artifact phải có identity/version, checksum và kích
thước được xác minh trước khi dùng; filesystem adapter không được nuốt một
filesystem collision thành dữ liệu hợp lệ. Thay đổi không thêm job lifecycle,
không đổi storage backend và không đưa local path vào domain contract.
