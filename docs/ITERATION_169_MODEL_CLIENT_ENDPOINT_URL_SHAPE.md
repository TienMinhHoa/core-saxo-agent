# Bằng chứng Iteration 169 — hình dạng URL endpoint model service

## Phạm vi

Theo `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, backend gọi external model service
qua LiteLLM-compatible HTTP request/response. Iteration này siết đúng boundary
transport: endpoint phải là absolute URL có scheme `http` hoặc `https` và có host.

## Thay đổi

- `LiteLLMModelClient` phân tích endpoint sau khi trim và bỏ trailing slash.
- Từ chối endpoint tương đối, scheme không phải HTTP(S), hoặc URL không có host
  trước khi thực hiện provider I/O.
- Giữ nguyên canonical endpoint hợp lệ và các guard control-character đã có.
- Thêm test hồi quy cho ba dạng endpoint sai.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_1_litellm_client.py`
- Full suite: chạy sau thay đổi; kết quả được ghi trong handoff iteration.
- Static: `uv run python -m compileall src tests` và `git diff --check`.

## Giới hạn xác minh

Chưa chạy live model-service smoke hoặc production parity vì checkout không có
endpoint, credential và production catalog được cấp quyền. Đây là kiểm chứng
offline của contract, không phải bằng chứng provider đang sẵn sàng.
