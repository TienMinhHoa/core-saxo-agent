# Iteration 185 - Contract runtime cho direct `AppSettings` construction

## Phạm vi

Theo mục 17.1 và 17.2 của `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`,
`AppSettings` là settings object dùng tại composition root. Iteration 184 đã
siết đường `AppSettings.from_environment`, nhưng caller vẫn có thể khởi tạo
dataclass trực tiếp với `NaN`, `Infinity`, số âm hoặc ratio vượt giới hạn.

## Thay đổi

- Thêm `AppSettings.__post_init__` để áp contract runtime cho toàn bộ float liên
  quan health-cache, health-timeout, LiteLLM timeout, retry backoff, jitter và
  circuit-breaker cooldown.
- Reject trực tiếp giá trị không hữu hạn, không đúng cận dương/không âm, hoặc
  jitter ratio lớn hơn `1.0` bằng `SettingsValidationError`.
- Giữ nguyên parser environment và các giá trị hợp lệ hiện có.

## Bằng chứng kiểm chứng

- `uv run pytest -q tests/test_phase_1_settings.py`: **42 passed**.
- `uv run pytest -q`: **760 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; Git chỉ cảnh báo chuyển line ending LF/CRLF trên
  Windows.

## Giới hạn

Đây là kiểm chứng offline với settings và fake dependencies. Live model-service
smoke và production parity vẫn chưa xác minh vì checkout chưa có endpoint,
credential và catalog production thật.
