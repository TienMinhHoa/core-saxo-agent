# Iteration 16 - bounded jitter cho retry model request

## Phạm vi

Lát cắt này hoàn thiện phần retry của `LiteLLMModelClient` theo yêu cầu kiến
trúc: exponential backoff có jitter, chỉ retry request có `idempotency_key`, và
không làm thay đổi ưu tiên `Retry-After` từ model service.

## Thay đổi

- Thêm `retry_jitter_ratio`, mặc định `0`, để giữ tương thích với cấu hình hiện tại.
- Jitter là phần cộng dương, bị giới hạn trong khoảng `0..ratio` của delay nền;
  delay nền vẫn là sàn retry.
- Cho phép inject `jitter_source` để test deterministic; runtime dùng
  `random.uniform`.
- Từ chối ratio ngoài `[0, 1]`, tránh cấu hình làm giảm delay hoặc tạo backoff
  không kiểm soát.
- `Retry-After` hợp lệ vẫn được chọn bằng `max(server_delay, local_delay)`.

## Bằng chứng

```text
uv run pytest tests/test_phase_1_litellm_client.py -q
21 passed

uv run pytest -q
297 passed, 2 skipped, 1 warning
```

Đã bao phủ exponential delay cũ, jitter deterministic và validation ratio.
`compileall` và `git diff --check` cũng thành công.
Live model-service smoke vẫn chưa thể chạy vì checkout chưa có endpoint và
credential thật; test HTTP mock không được dùng để thay thế bằng chứng live.
