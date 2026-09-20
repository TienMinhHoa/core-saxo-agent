# Iteration 15 — exponential backoff cho model request

## Phạm vi

Lát cắt này hoàn thiện phần retry của `LiteLLMModelClient` theo yêu cầu trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: delay local tăng theo cấp số nhân khi
các lần thử liên tiếp vẫn gặp lỗi retryable. Retry vẫn chỉ được phép khi
request có `idempotency_key`; request không có khóa vẫn chỉ chạy một lần.

## Thay đổi

- Delay local của lần retry thứ `n` là `retry_backoff_seconds * 2 ** (n - 1)`.
- `Retry-After` hợp lệ vẫn được ưu tiên nếu lớn hơn delay local đã tăng; giá trị
  âm, không parse được hoặc không hữu hạn vẫn quay về delay local.
- Bổ sung contract test cho chuỗi hai lần retry: `1.5` rồi `3.0` giây.

## Bằng chứng xác minh

```text
uv run pytest tests/test_phase_1_litellm_client.py -q
18 passed

uv run pytest -q
294 passed, 2 skipped, 1 warning
```

Đã chạy thêm `uv run python -m compileall -q src tests` và `git diff --check`;
cả hai đều thành công. Đây là bằng chứng offline; live model-service smoke vẫn
chưa thể chạy vì checkout chưa có endpoint và credential thật.

## Giới hạn

Lát cắt này không thêm jitter ngẫu nhiên để giữ contract test deterministic và
không thay đổi circuit-breaker, transport hay lifecycle của model service.
