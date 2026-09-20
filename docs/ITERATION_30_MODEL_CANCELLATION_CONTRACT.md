# Bằng chứng Iteration 30 — cancellation request model

## Phạm vi

Iteration này kiểm chứng một quy tắc async bắt buộc trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: khi client hủy request đang chờ
model service, cancellation phải đi xuyên qua LiteLLM client; client không được
tự retry request đã bị hủy và metrics không được giữ trạng thái `in_flight`.

## Thay đổi

- Bổ sung contract test `test_litellm_client_propagates_cancellation_without_retry_or_stuck_metrics`.
- Test dùng `httpx.MockTransport` với handler chờ vô hạn, hủy task group khi
  request đã bắt đầu, rồi xác minh chỉ có một request, không có failure event giả
  và `in_flight` trở về `0`.
- Không thêm job lifecycle, persisted cancellation state hoặc local GPU fallback.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_1_litellm_client.py -q
24 passed
```

Cancellation hiện được propagate bởi async HTTP stack và được cleanup qua
`finally` của `LiteLLMModelClient.invoke`; live model-service smoke vẫn chưa thể
chạy vì checkout chưa có endpoint, credential và production catalog thật.
