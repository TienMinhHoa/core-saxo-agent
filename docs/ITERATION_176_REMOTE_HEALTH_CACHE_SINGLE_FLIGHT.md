# Iteration 176 — Gộp các lần refresh health đồng thời

## Phạm vi

Tiếp tục củng cố tiêu chí health/cache trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.
Đơn vị lần này là bảo đảm nhiều request health đến cùng lúc không tạo nhiều request
đồng thời tới model service khi cache đã hết hạn.

## Thay đổi

- Bổ sung contract test concurrency cho `CachedRemoteGpuGateway`.
- Test giữ lần refresh đầu đang chờ, khởi chạy request thứ hai, rồi xác minh cả hai
  nhận cùng kết quả và upstream chỉ được gọi đúng một lần.
- Không thay đổi public API hay thêm job lifecycle; `asyncio.Lock` hiện hữu được
  kiểm chứng như cơ chế single-flight tại cache boundary.

## Bằng chứng kiểm chứng

- Targeted: `uv run pytest tests/test_phase_1_remote_gpu_http.py --basetemp=.pytest-tmp-176`
  — **10 passed**.
- Full suite: `uv run pytest --basetemp=.pytest-tmp-176-full` — **741 passed, 3 skipped,
  1 warning**.
- Static: `uv run python -m compileall -q src tests` và `git diff --check` — **đạt**.
- Live model-service smoke và production parity vẫn chưa xác minh vì checkout chưa có
  endpoint, credential và catalog production thật.

## Kết luận

Cache health hiện có bằng chứng offline rằng refresh đồng thời được coalesced, giảm
nguy cơ health endpoint tạo burst request lên model service sau khi TTL hết hạn.
