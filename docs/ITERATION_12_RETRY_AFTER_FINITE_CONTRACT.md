# Iteration 12 — giới hạn Retry-After về giá trị hữu hạn

## Phạm vi

Hoàn thiện contract retry của `LiteLLMModelClient`: header `Retry-After` chỉ
được dùng khi parse được thành số giây hữu hạn và không âm. Giá trị `nan`,
`inf`, số âm hoặc chuỗi không phải số phải quay về local backoff để tránh
delay vô hạn hoặc hành vi không xác định.

## Thay đổi

- Bổ sung kiểm tra `math.isfinite` trong hàm tính delay retry.
- Bổ sung regression test cho `not-a-number`, `-1`, `nan` và `inf`.
- Giữ nguyên ưu tiên `max(server_delay, retry_backoff_seconds)` đối với giá trị
  hợp lệ.

## Bằng chứng xác minh

```text
uv run pytest tests/test_phase_1_litellm_client.py -q
15 passed

uv run pytest -q
290 passed, 2 skipped, 1 warning

uv run python -m compileall -q src tests
```

`git diff --check` được chạy sau khi hoàn tất thay đổi. Đây vẫn là xác minh
offline; live model-service smoke chưa thể chạy vì checkout chưa có endpoint và
credential thật.
