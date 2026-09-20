# Iteration 34 - xác thực integrity khi đọc artifact

## Phạm vi

Khóa khoảng trống trong yêu cầu artifact immutable: `put()` đã kiểm tra
`size_bytes` và `sha256`, nhưng `get()` trước đây trả bytes trên filesystem mà
không xác thực lại metadata.

## Thay đổi

- Bổ sung test contract: sau khi artifact đã được ghi, nếu bytes trên đĩa bị
  thay đổi thì `get()` phải ném `ValueError` thay vì trả dữ liệu tampered.
- `LocalArtifactRepository.get()` đọc bytes trong bounded I/O limiter, sau đó
  dùng cùng validator kích thước/checksum trước khi trả kết quả.
- Giữ nguyên `FileNotFoundError`, atomic write và path-safety behavior hiện có.

## Bằng chứng kiểm thử

- Targeted artifact contract: `6 passed`.
- Full suite: `327 passed, 2 skipped, 1 warning`.
- `uv run python -m compileall -q src tests`: thành công.
- `git diff --check`: thành công.
- Live model-service smoke chưa chạy: checkout vẫn không có endpoint,
  credential và production catalog được cấp quyền.

## Kết luận

Artifact repository hiện kiểm tra integrity ở cả lúc ghi và lúc đọc; điều này
đáp ứng tốt hơn tiêu chí controlled artifact có size và checksum, nhưng không
thay thế live smoke hoặc production retrieval parity.
