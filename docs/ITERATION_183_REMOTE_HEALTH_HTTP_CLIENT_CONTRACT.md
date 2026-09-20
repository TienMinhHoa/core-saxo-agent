# Iteration 183 — Hợp đồng dependency HTTP của remote health

## Phạm vi

Tiếp tục lựa chọn Clean Code trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
`HttpRemoteGpuGateway` phải fail-fast tại composition boundary nếu HTTP client
được inject nhưng không có phương thức `get` callable.

## Thay đổi

- Bổ sung guard tại constructor của `HttpRemoteGpuGateway`.
- Bổ sung regression test chứng minh dependency sai bị từ chối trước khi có
  network I/O hoặc health request.

## Bằng chứng xác minh

- Test đỏ trước implementation: test mới fail vì dependency sai vẫn được nhận.
- Test xanh sau implementation: `uv run pytest -q tests/test_phase_1_remote_gpu_http.py::test_health_rejects_http_client_without_callable_get`.
- Sẽ chạy full suite, compileall và `git diff --check` trước khi kết luận iteration.

## Giới hạn

Đây là kiểm chứng offline với fake dependency; chưa phải live smoke tới
model-service thật. Endpoint, credential và production catalog vẫn chưa có trong
checkout này nên chưa thể xác minh production parity.
