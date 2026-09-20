# Iteration 174 — siết kiểu response của health model-service

## Mục tiêu

Tiếp tục yêu cầu của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` về capability-health an toàn: adapter health phải fail-closed khi transport trả về object không phải `httpx.Response`, thay vì làm rơi `AttributeError` ra ngoài endpoint.

## Thay đổi

- `HttpRemoteGpuGateway.health()` xác nhận response sau `await` là `httpx.Response` trước khi gọi `raise_for_status()` và `json()`.
- Response sai kiểu được chuyển thành trạng thái công khai `unavailable`, giữ nguyên nguyên tắc không rò payload/provider exception.
- Bổ sung contract test với HTTP client giả trả về object sai kiểu; đồng thời loại import trùng trong test.

## Bằng chứng kiểm chứng

- Targeted: `uv run pytest tests/test_phase_1_remote_gpu_http.py` — **8 passed**.
- Full suite: `uv run pytest` — **739 passed, 3 skipped, 1 warning**.
- `python -m compileall -q src tests` — đạt.
- `git diff --check` — đạt.
- Live model-service smoke chưa thực hiện vì checkout vẫn không có endpoint, credential và production catalog được cấp quyền.

## Kết luận

Đơn vị refactor này hoàn tất boundary contract offline: health adapter không phụ thuộc vào việc provider luôn trả đúng object runtime. Stop condition toàn bộ chưa đạt vì live smoke và production golden parity vẫn còn blocker môi trường.
