# Bằng chứng Phase 1 — circuit breaker cho model request

## Phạm vi

`LiteLLMModelClient` nay có circuit breaker tùy chọn ở đúng boundary gọi model.
Sau số lần lỗi retryable liên tiếp đã cấu hình, request tiếp theo bị chặn trước
khi gọi HTTP. Sau cooldown, client cho phép một request thử lại; request thành
công sẽ reset bộ đếm.

Circuit breaker mặc định tắt (`circuit_breaker_failure_threshold=0`) để giữ
tương thích với các composition root hiện tại; deployment có thể bật bằng cấu
hình adapter mà không đưa policy vào application use case.

## Bằng chứng kiểm thử

- `tests/test_phase_1_litellm_client.py` chứng minh hai lỗi `503` mở mạch,
  request thứ ba nhận `ModelCircuitOpenError` và không phát sinh HTTP call.
- Sau cooldown, request được phép đi qua lại.
- Các rule trước đó vẫn giữ nguyên: lỗi auth/contract không retry; timeout,
  network error và `429/5xx` là nhóm retryable.

## Giới hạn đã biết

Trạng thái circuit nằm trong một process/client instance. Multi-worker hoặc
distributed circuit state cần một adapter coordination riêng, không thuộc lát
cắt này.
