# Iteration 171 — Siết thành phần endpoint của LiteLLM client

## Kết quả

`LiteLLMModelClient` nay fail-closed khi endpoint chứa query string, fragment
hoặc port không hợp lệ. Điều này đồng bộ với validation tại `AppSettings` và
ngăn cấu hình URL ngoài ý muốn đi vào HTTP transport.

## Bằng chứng

- TDD: thêm 3 trường hợp contract cho query, fragment và invalid port trong
  `tests/test_phase_1_litellm_client.py`.
- Regression targeted: `uv run pytest tests/test_phase_1_litellm_client.py`
  đạt **55 passed**.
- Full suite: `uv run pytest` đạt **736 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` đạt.
- `git diff --check` đạt.

## Giới hạn còn lại

Live model-service smoke và production golden parity chưa chạy vì checkout
chưa có endpoint, credential và catalog production thật.
