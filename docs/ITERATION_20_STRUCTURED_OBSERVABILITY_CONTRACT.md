# Iteration 20 — contract observability có cấu trúc

## Mục tiêu

Đáp ứng phần observability của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` bằng
một contract provider-independent cho event pipeline/model. Lát cắt này chỉ
allowlist metadata an toàn; không ghi request payload, response đầy đủ, API key,
raw PDF hay image bytes.

## Thay đổi

- Thêm `StructuredEvent` với correlation ID, task/model, attempt, duration,
  input/output counts, result và reason code.
- Validate các trường định danh và metric không âm; loại bỏ trường `None` khi
  chuyển sang dictionary để logger downstream dùng trực tiếp.
- Thêm `EventSink` port và `InMemoryEventSink` deterministic cho contract test.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_1_observability_contract.py`: đạt.
- Full suite: `309 passed, 2 skipped, 1 warning`.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.

## Giới hạn còn lại

Iteration này mới khóa contract và sink test; wiring logger/metrics production
và live model-service smoke vẫn cần endpoint, credential, policy TLS và catalog
production thật. Không dùng fake HTTP để tuyên bố live verification.
