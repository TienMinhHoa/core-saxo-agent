# Iteration 21 — nối structured event vào model client

## Phạm vi

Tiếp tục contract observability của Iteration 20 bằng cách nối `EventSink` vào
`LiteLLMModelClient`. Mỗi lần gọi model thành công hoặc thất bại hiện có thể
phát một event an toàn, không chứa prompt, response thô hay secret.

## Thay đổi

- `LiteLLMModelClient` nhận `event_sink` tùy chọn qua dependency injection.
- Event thành công ghi task, model, correlation, số attempt, thời lượng, số
  trường input/output và `result=success`.
- Lỗi transport/HTTP ghi event thất bại với loại exception làm `reason_code`;
  payload response không được đưa vào event.
- Số attempt được trả nội bộ từ retry loop để event phản ánh retry thực tế.
- Correlation ưu tiên `metadata.correlation_id`, sau đó dùng idempotency key;
  nếu cả hai không có thì dùng nhãn cố định không chứa dữ liệu người dùng.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_1_litellm_client.py tests/test_phase_1_observability_contract.py
28 passed
```

Đã bổ sung test cho event thành công và event thất bại, đồng thời giữ nguyên
các test retry, idempotency, circuit breaker và validation hiện có.

## Giới hạn còn lại

- Chưa có live model-service smoke vì checkout chưa được cung cấp endpoint,
  credential và catalog production.
- Event sink mới được wiring ở client; composition root chưa mặc định chọn
  sink ghi log/metrics production. Đây là đơn vị kế tiếp phù hợp.
