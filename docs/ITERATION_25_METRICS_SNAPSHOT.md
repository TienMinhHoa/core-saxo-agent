# Iteration 25 - snapshot metrics quan sát được

## Phạm vi

Hoàn thiện một lát cắt nhỏ của mục 19.3 trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: consumer vận hành cần đọc toàn bộ
metrics tại cùng một thời điểm, không phải ghép nhiều getter có thể nhìn thấy
các trạng thái khác nhau.

## Thay đổi

- Thêm `MetricsSnapshot` bất biến cho counts, duration, in-flight và peak
  concurrency.
- Thêm `EventMetrics.snapshot()` lấy snapshot dưới cùng một lock rồi sao chép
  các collection thành tuple; cập nhật metrics sau đó không làm thay đổi
  snapshot đã phát hành.
- Bổ sung contract test cho tính nhất quán và tính tách rời của snapshot.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_1_observability_contract.py` -> **9 passed**.
- `uv run pytest` -> **316 passed, 2 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` -> thành công.
- `git diff --check` -> thành công.

## Giới hạn còn lại

Snapshot vẫn là metrics in-process; chưa thêm exporter Prometheus hoặc live
model-service smoke. Live smoke tiếp tục cần endpoint, credential và catalog
production thật.
