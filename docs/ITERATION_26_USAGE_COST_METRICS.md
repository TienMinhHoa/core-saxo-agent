# Iteration 26 — token usage và cost trong observability

## Phạm vi

Hoàn thiện lát cắt nhỏ của mục 19.1 và 19.3 trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: structured event có thể mang
`input_tokens`, `output_tokens` và `cost_usd` khi provider trả về usage.
Các trường đều tùy chọn để không phá vỡ event cũ hoặc các provider chưa cung
cấp usage.

## Thay đổi

- `StructuredEvent` validate usage không âm và chỉ serialize các trường có giá
  trị; không thêm payload, response hay secret vào event.
- `EventMetrics` cộng dồn token input/output và cost theo task, đồng thời đưa
  chúng vào `MetricsSnapshot` bất biến.
- Bổ sung contract tests cho serialization, validation, accumulation và giữ
  tương thích event không có usage.

## Bằng chứng xác minh

- `uv run pytest tests/test_phase_1_observability_contract.py -q`: **14 passed**.
- Full suite: **321 passed, 2 skipped, 1 warning**; `compileall` và
  `git diff --check` thành công.
- Chưa khẳng định provider live trả usage; model-service endpoint/credential
  thật vẫn là blocker đã ghi trong acceptance status.

## Giới hạn có chủ đích

Iteration này chỉ mở rộng contract và in-process metrics. Việc map usage từ
response LiteLLM cụ thể sẽ thực hiện riêng sau khi contract response của
model-service được cung cấp và xác minh.
