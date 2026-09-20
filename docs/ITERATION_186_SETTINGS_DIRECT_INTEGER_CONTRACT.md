# Iteration 186 — contract số nguyên khi khởi tạo `AppSettings`

## Kết quả

Đã đồng bộ validation giữa `AppSettings.from_environment()` và khởi tạo trực tiếp
`AppSettings(...)`. Các trường số nguyên hiện fail-closed nếu nhận `bool`, `float`,
chuỗi, giá trị âm, hoặc `0` ở trường bắt buộc dương.

Phạm vi gồm giới hạn đồng thời, thời gian lưu giữ, số lần thử LiteLLM, ngưỡng
circuit breaker, kích thước embedding và giới hạn upload. Ngưỡng circuit breaker
vẫn cho phép `0` vì đây là giá trị tắt tính năng theo contract hiện tại.

## Bằng chứng

- TDD: thêm 6 ca regression vào `tests/test_phase_1_settings.py`.
- Targeted: `uv run pytest -q tests/test_phase_1_settings.py` — dự kiến 48 passed.
- Full suite, `compileall` và `git diff --check` được chạy sau khi hoàn tất thay đổi.
- Live model-service smoke và production parity vẫn chưa thể xác minh vì checkout
  chưa có endpoint, credential và catalog production được cấp phép.
