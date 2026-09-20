# Phase 1 — Cấu hình LiteLLM tập trung

## Phạm vi lát cắt

Iteration 20 hoàn thiện phần cấu hình còn thiếu của Phase 1 trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: endpoint, model profile, timeout và
retry policy của model service được đọc một lần tại composition root và truyền
vào `LiteLLMModelClient`. Use case không đọc environment và không biết URL HTTP.

## Thay đổi đã thực hiện

- `AppSettings` có các trường typed `litellm_endpoint`,
  `litellm_model_profile`, `litellm_timeout_seconds`, `litellm_max_attempts`
  và `litellm_retry_backoff_seconds`.
- Endpoint mặc định được suy ra từ remote GPU base URL; endpoint ghi đè phải là
  HTTPS URL không credential, query hoặc fragment.
- Timeout phải dương; số lần thử phải dương; backoff không âm; profile không
  được rỗng. Các lỗi đều fail sớm bằng `SettingsValidationError`.
- `create_app()` truyền toàn bộ transport policy vào một `LiteLLMModelClient`
  dùng chung. Không tạo client mới trong request handler.

## Bằng chứng kiểm thử

Lệnh:

```text
uv run pytest tests/test_phase_1_settings.py tests/test_phase_1_composition_root.py
```

Kết quả: **23 passed**, 1 cảnh báo deprecation từ dependency Starlette; không
có lỗi test.

Các test chứng minh default an toàn, override typed values và composition root
thực sự dùng endpoint/timeout/max attempts/backoff đã cấu hình.
