# Iteration 248 — khóa boundary transport cho task adapter

## Mục tiêu

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: task adapter OCR/VLM/embedding/LLM phải gọi qua `LiteLLMModelClient` và không tự mở HTTP/provider transport.

## Thay đổi

- Bổ sung guard AST cho bốn remote task adapter của `chat`, `extraction`, `ingestion` và `tagging`.
- Bổ sung guard toàn source mới: `httpx` chỉ xuất hiện ở `platform` hoặc composition root `app`; feature module không được import trực tiếp.
- Không đổi behavior runtime; đây là enforcement test để ngăn dependency drift quay lại.

## Bằng chứng

- Targeted: `pytest -q tests/test_phase_7_dependency_enforcement.py` — 10 tests pass.
- Full suite: **931 passed, 18 skipped, 1 warning**; `compileall` và `git diff --check` đều pass.
- `git diff --check` được chạy để kiểm tra whitespace.

## Giới hạn còn lại

Live model-service smoke và production golden parity vẫn chưa xác minh vì checkout không có endpoint, credential và production catalog thật. Đây là blocker môi trường, không phải lý do để thêm fallback GPU/local provider vào backend.
