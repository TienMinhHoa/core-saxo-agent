# Bằng chứng iteration 17: wiring cấu hình retry model-service

## Phạm vi

Lát refactor này hoàn thiện đường đi cấu hình từ `AppSettings` tới
`LiteLLMModelClient` cho các policy retry/circuit-breaker đã có ở adapter:

- `SAXO_LITELLM_RETRY_JITTER_RATIO` trong khoảng `0..1`;
- `SAXO_LITELLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD` là số nguyên không âm;
- `SAXO_LITELLM_CIRCUIT_BREAKER_COOLDOWN_SECONDS` là số dương.

Composition root truyền các giá trị đã validate vào model client. Giá trị mặc
định giữ behavior cũ: jitter tắt, circuit-breaker tắt và cooldown 30 giây.

## Thay đổi đã thực hiện

- Bổ sung parser typed trong `src/saxophone/app/settings.py`.
- Bổ sung wiring trong `src/saxophone/app/factory.py`.
- Bổ sung property quan sát được của client để contract test không đọc private
  state.
- Bổ sung test cho default, giá trị tường minh, wiring và các giá trị biên bị
  từ chối trong `tests/test_phase_1_settings.py` và
  `tests/test_phase_1_composition_root.py`.

## Bằng chứng kiểm tra

- Targeted settings/composition tests: đạt.
- Full offline suite: `301 passed, 2 skipped, 1 warning`.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; chỉ có cảnh báo line-ending thông thường từ Git.
- Chưa thực hiện live model-service smoke vì checkout vẫn không có endpoint và
  credential thật; test HTTP giả chỉ xác minh contract offline.
