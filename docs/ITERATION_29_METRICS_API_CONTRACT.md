# Bằng chứng Iteration 29 — API metrics

## Phạm vi

Iteration này hoàn thiện một đơn vị nhỏ của mục observability trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: snapshot metrics đã được thu thập
trong process nay có một API diagnostics ổn định để đọc.

## Thay đổi

- Thêm `GET /api/v1/metrics` trong composition root.
- Endpoint chỉ trả `MetricsSnapshot` bất biến, được chuyển qua `dataclasses.asdict`;
  không trả request payload, token bí mật, URL hay dữ liệu provider.
- Trạng thái trả về là `ready` khi metrics được wiring mặc định; với custom event
  sink không có metrics, endpoint trả `disabled` và `snapshot: null`.
- Thêm API contract test xác minh counts, duration, token/cost fields rỗng,
  in-flight và peak concurrency được serialize thành JSON an toàn.

## Bằng chứng kiểm chứng

```text
uv run pytest tests/test_phase_7_api_routes.py -q
22 passed, 1 warning

uv run pytest -q
324 passed, 2 skipped, 1 warning

uv run python -m compileall -q src tests
PASS

git diff --check
PASS (chỉ cảnh báo chuẩn hóa LF/CRLF của Git trên Windows)
```

## Giới hạn còn lại

Metrics hiện vẫn là in-process snapshot; chưa phải exporter Prometheus phân tán.
Live model-service smoke và production catalog vẫn cần endpoint/credential thật,
không được suy diễn từ test fake.
