# Iteration 18 — Trạng thái capability theo model service

## Mục tiêu

Đồng bộ health contract với `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: capability
đã được compose nhưng model service đang `degraded` hoặc `unavailable` không
được quảng bá là `ready`.

## Thay đổi

- Thêm hàm `_capability_status` tại composition root.
- Capability chưa được compose vẫn trả `disabled`.
- Capability đã được compose chỉ trả `ready` khi model service `ready`; nếu
  model service `degraded` hoặc `unavailable`, capability trả `degraded`.
- Giữ nguyên hai trường tương thích `model_service` và `remote_gpu`.

## Bằng chứng

- Test hồi quy mới:
  `test_health_marks_configured_model_capabilities_degraded_when_service_is_unavailable`.
- Test hiện có xác nhận model service `ready` vẫn giữ extraction `ready` và
  capability chưa compose vẫn `disabled`.
- Kiểm tra targeted: `uv run pytest tests/test_phase_7_api_routes.py -q` — đạt
  sau thay đổi (19 passed, 1 warning).
- Kiểm tra toàn bộ: `uv run pytest -q` — đạt (302 passed, 2 skipped, 1 warning).
- `uv run python -m compileall -q src tests` và `git diff --check` — đạt.
- Live model-service smoke chưa thực hiện vì checkout chưa có endpoint và
  credential thật; test gateway là contract offline, không thay thế provider
  thật.
