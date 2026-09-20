# Phase 1 - Timeout và retry cho LiteLLM model client

## Phạm vi

Iteration 18 hoàn thiện một lát nhỏ của `LiteLLMModelClient`: mọi request có
timeout rõ ràng và số lần thử tối đa được giới hạn. Client chỉ retry lỗi tạm
thời ở tầng mạng hoặc HTTP (`408`, `429`, `5xx`); lỗi xác thực và contract
không bị retry mù. Không tạo job ID, queue, polling hay trạng thái retry được
lưu bền vững.

## Thay đổi

- Thêm `timeout_seconds`, `max_attempts` và `retry_backoff_seconds` vào adapter.
- Giữ nguyên request/response envelope typed và validation `ModelResponse`.
- Không retry lỗi `401` và các lỗi HTTP contract không tạm thời.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_1_litellm_client.py tests/test_phase_1_model_client_contract.py`: **11 passed**.
- Test retry xác nhận lỗi `503` thử lại đúng số lần giới hạn và sau đó map response hợp lệ.
- Test auth xác nhận `401` chỉ gọi provider một lần.

## Ranh giới còn lại

Adapter vẫn chưa được nối vào `AppContainer`/composition root và settings môi
trường. Đây là lát tiếp theo; iteration này chỉ thay đổi policy transport và
không mở rộng sang use case hay lifecycle provider.
