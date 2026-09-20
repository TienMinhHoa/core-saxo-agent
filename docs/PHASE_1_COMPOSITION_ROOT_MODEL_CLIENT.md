# Phase 1 - Nối model client vào composition root

## Phạm vi

Iteration 19 hoàn tất một lát refactor nhỏ của Phase 1: `AppContainer` sở hữu
`LiteLLMModelClient` dùng chung, được tạo tại composition root và không bị khởi
tạo khi import module. Remote GPU gateway và model client có thể được thay bằng
fake qua `AppOverrides` để unit/API test không cần gọi dịch vụ bên ngoài.

## Thay đổi

- `AppContainer` công khai `model_client` như một application dependency.
- Production composition tạo một `httpx.AsyncClient` dùng chung cho
  `HttpRemoteGpuGateway` và `LiteLLMModelClient`.
- FastAPI lifespan đóng client dùng chung khi app shutdown.
- Test override có thể inject cả remote gateway và model client; health test
  không cần biết HTTP/model SDK cụ thể.
- Endpoint model hiện được suy ra từ remote GPU base URL với suffix
  `/v1/invoke`; đây là compatibility wiring tạm thời, chưa phải API contract
  cuối cùng của model service.

## Bằng chứng kiểm thử

Lệnh đã chạy:

```text
uv run pytest tests/test_phase_1_composition_root.py tests/test_phase_1_litellm_client.py tests/test_phase_1_model_client_contract.py
17 passed, 1 warning
```

Các test xác nhận composition root giữ dependency typed, production có đúng
một HTTP client được đóng theo lifespan, fake model client được inject và
LiteLLM envelope/retry/validation vẫn hoạt động.

## Ranh giới còn lại

Chưa chạy live model service và chưa thêm các capability route. Lát tiếp theo
nên đưa model endpoint, model profile, timeout và retry policy vào
`AppSettings`, thay vì tiếp tục suy ra endpoint từ remote GPU URL.
