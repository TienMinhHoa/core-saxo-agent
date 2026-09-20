# Phase 1 — Áp dụng cấu hình xác minh TLS cho remote model service

## Phạm vi

Lát cắt Clean Code này đóng một khoảng trống trong composition root: biến
`SAXO_REMOTE_GPU_TLS_VERIFY` đã được parse và validate nhưng chưa được truyền
vào HTTP client dùng chung. Từ nay `create_app()` truyền giá trị này vào
`httpx.AsyncClient(verify=...)`, để policy TLS được áp dụng thật ở boundary hạ
tầng thay vì chỉ tồn tại trong settings.

## Contract đã khóa

- Mặc định `SAXO_REMOTE_GPU_TLS_VERIFY=true` giữ xác minh chứng thư.
- Khi cấu hình `false`, shared client nhận đúng `verify=False`.
- Gateway và LiteLLM client tiếp tục dùng cùng một HTTP client; không tạo thêm
  client riêng hoặc đưa TLS policy vào application use case.

## Bằng chứng kiểm chứng

- `uv run pytest -q tests/test_phase_1_composition_root.py::test_default_composition_applies_remote_gpu_tls_verification_setting`
  → **1 passed**.
- `uv run python -m compileall -q src tests` → **pass**.
- `git diff --check` → **pass**.
- `uv run pytest -q` → **255 passed, 2 skipped, 1 warning**. Hai test skip là
  do thiếu Gradio và sample source, không liên quan lát cắt này.

## Giới hạn còn lại

Đây là kiểm chứng offline ở composition boundary. Chưa có live smoke với
model-service thật; việc đó cần endpoint và chứng thư được cung cấp riêng.
