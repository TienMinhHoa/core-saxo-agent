# Iteration 24 - metric concurrency cho model service

## Phạm vi

Hoàn thiện một phần nhỏ của mục 19.3 trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: đo số model request đang chạy và
đỉnh concurrency theo từng task. Không thêm exporter Prometheus hay backend
metrics phân tán; đó vẫn là phạm vi triển khai sau.

## Thay đổi

- `EventMetrics` có `request_started`, `request_finished`, `in_flight` và
  `max_concurrency`, được bảo vệ bằng lock để đọc/ghi nhất quán.
- `LiteLLMModelClient.invoke` bắt đầu/kết thúc metric trong `try/finally`, nên
  cả lỗi transport, lỗi validation và circuit-open đều không để lại request
  đang chạy giả.
- Composition root truyền cùng instance metrics vào model client và
  `LoggingEventSink`; không tạo thêm lifecycle/job endpoint.
- Thêm contract test chứng minh peak concurrency bằng 2 và in-flight quay về 0.

## Bằng chứng kiểm chứng

- `uv run pytest tests/test_phase_1_observability_contract.py tests/test_phase_1_litellm_client.py tests/test_phase_1_composition_root.py`
  -> **53 passed**.
- `uv run pytest` -> **315 passed, 2 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` -> thành công.
- `git diff --check` -> thành công.

## Giới hạn còn lại

Metrics hiện vẫn là in-process. Live model-service smoke và production
catalog chưa thể xác minh vì checkout không có endpoint/credential thật.
