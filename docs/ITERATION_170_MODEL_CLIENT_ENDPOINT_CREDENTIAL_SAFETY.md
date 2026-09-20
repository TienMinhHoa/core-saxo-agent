# Bằng chứng Iteration 170 — endpoint model service không chứa user-info

## Phạm vi

Theo `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, backend gọi external model service
qua HTTPS và giữ credential ở server side. Endpoint cấu hình không nên chứa
username/password trong URL, vì URL có thể bị log hoặc truyền qua các lớp quan
trắc hạ tầng ngoài ý muốn.

## Thay đổi

- `LiteLLMModelClient` phân tích URL sau khi chuẩn hóa và fail-closed nếu URL có
  username hoặc password.
- Bổ sung regression tests cho URL có đủ password, chỉ password và chỉ username.
- Không thay đổi endpoint hợp lệ không có user-info hoặc cơ chế bearer-token hiện có.

## Kiểm chứng

- Targeted: `uv run pytest tests/test_phase_1_model_client_contract.py` — **40 passed**.
- Full suite: `uv run pytest` — **733 passed, 3 skipped, 1 warning**.
- Static: `uv run python -m compileall src tests` và `git diff --check` — đạt.

## Giới hạn

Live model-service smoke và production parity chưa thể xác minh vì checkout chưa
có endpoint, credential và catalog production thật. Thay đổi này chỉ chứng minh
contract offline tại client boundary.
