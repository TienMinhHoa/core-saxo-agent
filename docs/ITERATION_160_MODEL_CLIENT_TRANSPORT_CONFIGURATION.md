# Bằng chứng iteration 160 — cấu hình transport của model client

## Phạm vi

Siết boundary của `LiteLLMModelClient` theo hướng Clean Code: cấu hình
`endpoint` và `bearer_token` phải là chuỗi; endpoint được loại khoảng trắng
thừa trước khi bỏ dấu `/` cuối. Mục tiêu là tránh `AttributeError` mơ hồ và
không gửi request tới URL sai do cấu hình có khoảng trắng.

## Thay đổi

- Constructor fail-closed với giá trị không phải chuỗi cho `endpoint` hoặc
  `bearer_token`.
- Endpoint được canonicalize bằng `strip()` rồi `rstrip("/")`.
- Bổ sung regression tests cho sai kiểu và endpoint có whitespace/trailing slash.

## Kiểm chứng

- Targeted: `uv run pytest tests/test_phase_1_model_client_contract.py` — **37
  passed**.
- Full suite: `uv run pytest -q` — **702 passed, 3 skipped, 1 warning**.
- Static: `uv run python -m compileall -q src tests` và `git diff --check` —
  **đạt**.

## Giới hạn bằng chứng

Đây là kiểm chứng offline. Live model-service smoke và production parity vẫn
chưa thể xác minh vì checkout chưa có endpoint, credential và catalog production.
