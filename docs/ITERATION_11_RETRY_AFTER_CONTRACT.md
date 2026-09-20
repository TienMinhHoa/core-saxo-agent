# Iteration 11 — Retry-After cho model-service

## Phạm vi

Hoàn thiện một lát nhỏ trong contract gọi model-service: khi LiteLLM-compatible
endpoint trả lỗi transient có header `Retry-After` dạng số giây, client phải chờ
ít nhất khoảng thời gian provider yêu cầu trước lần thử tiếp theo. Retry vẫn bị
giới hạn bởi `max_attempts`; lỗi contract/auth không được retry.

## Thay đổi

- `LiteLLMModelClient` đọc `Retry-After` cho các response retryable.
- Delay hiệu dụng là `max(retry_backoff_seconds, Retry-After)`; header thiếu,
  âm hoặc không hợp lệ quay về backoff local.
- Thêm regression test với HTTP 429 để chứng minh request thứ hai chỉ chạy sau
  delay 3 giây theo header, không ngủ thật trong test.

## Bằng chứng xác minh

```text
uv run pytest tests/test_phase_1_litellm_client.py
uv run python -m compileall -q src tests
git diff --check
```

Kết quả chi tiết sẽ được ghi bổ sung vào `REFACTOR_ACCEPTANCE_STATUS.md` sau
khi các lệnh trên chạy xong.

## Giới hạn còn lại

Đây là xác minh offline bằng `httpx.MockTransport`; chưa phải live smoke với
model-service thật. Endpoint và credential thật vẫn cần được cung cấp riêng.
