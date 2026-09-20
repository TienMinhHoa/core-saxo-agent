# Bằng chứng Iteration 177: TTL cache health phải hữu hạn

## Phạm vi

Tiếp tục hardening nhỏ tại `CachedRemoteGpuGateway`, thuộc capability-health
cache của mục 17.3 trong `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.

## Thay đổi

- Constructor nay reject `ttl_seconds` là `NaN`, dương vô hạn hoặc âm vô hạn.
- Contract lỗi thống nhất là `ValueError("ttl_seconds must be finite and positive")`.
- TTL hợp lệ vẫn phải lớn hơn `0`, nên behavior cache hit, hết hạn và single-flight
  không thay đổi.

## Bằng chứng kiểm thử

- Đã thêm test TDD cho cả ba giá trị không hữu hạn.
- Trước implementation: test mới fail đúng vì constructor chấp nhận `NaN`/infinity.
- Sau implementation: `uv run pytest tests/test_phase_1_remote_gpu_http.py -q`
  đạt **12 passed**.
- Full suite: `uv run pytest -q` đạt **742 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` và `git diff --check` đều đạt.

## Giới hạn còn lại

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout chưa có endpoint, credential và catalog production thật.
