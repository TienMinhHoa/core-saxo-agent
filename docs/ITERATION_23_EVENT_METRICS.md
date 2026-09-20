# Iteration 23 - metrics tu structured events

## Pham vi

Bo sung lat cat nho cho muc 19.3 cua `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
ghi nhan so luong request theo task/result va duration cua model request.

## Thay doi

- Them `EventMetrics` voi counter theo `(event name, task, result)` va danh sach
  duration theo task.
- `LoggingEventSink` cap nhat metrics truoc khi ghi structured log; khong dua
  payload, response hay secret vao metrics.
- Composition root tao mot `EventMetrics` cung voi `LoggingEventSink` mac dinh
  va expose qua `AppContainer.metrics`.
- Them contract tests cho counter, duration va wiring.

## Bang chung kiem chung

- `uv run pytest tests/test_phase_1_observability_contract.py tests/test_phase_1_composition_root.py`
  -> 29 passed.
- `uv run pytest` -> 314 passed, 2 skipped, 1 warning.
- `uv run python -m compileall -q src tests` -> thanh cong.
- `git diff --check` -> thanh cong.

## Gioi han con lai

Metrics hien la in-process va phuc vu contract/runtime quan sat co ban; chua
phai exporter Prometheus hay backend metrics phan tan. Live model-service smoke
van chua duoc xac minh vi checkout thieu endpoint, credential va production
catalog that.
