# Iteration 179 — contract kiểu kết quả của health cache

## Phạm vi

Tiếp tục hardening `CachedRemoteGpuGateway` theo kiến trúc Clean Code trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Dependency `gateway` đã được inject
qua port, vì vậy cache phải kiểm tra runtime type của kết quả trước khi lưu và
trả kết quả ra application layer.

## Thay đổi

- `CachedRemoteGpuGateway.health()` fail-closed bằng `TypeError` nếu gateway
  trả về object không phải `RemoteGpuHealth`.
- Kết quả sai kiểu không được ghi vào cache, tránh việc một response malformed
  tồn tại hết TTL và lan sang readiness endpoint.
- Bổ sung test TDD cho gateway trả về mapping thay vì typed health result.

## Bằng chứng kiểm thử offline

- `uv run pytest tests/test_phase_1_remote_gpu_http.py -q`: **14 passed**.
- `uv run pytest -q`: **745 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; chỉ còn cảnh báo line ending CRLF của Git trên
  các file Windows, không có whitespace error.

## Giới hạn xác minh

Live model-service smoke và production golden parity chưa thể chạy trong
checkout này vì chưa có endpoint, credential và production catalog thật.
