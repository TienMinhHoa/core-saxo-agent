# Iteration 175 — Làm sạch capability trong health model-service

## Phạm vi

Tiếp tục harden boundary `HttpRemoteGpuGateway` theo mục 17.3 và 20 của
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Health response chỉ được đưa các tên
capability an toàn vào `RemoteGpuHealth`; chuỗi chứa control character không được
đi vào trạng thái công khai.

## Thay đổi

- `_parse_capabilities()` bỏ qua capability không phải chuỗi, rỗng sau trim,
  trùng lặp hoặc chứa ASCII control character (C0 và DEL).
- Bổ sung regression test chứng minh newline/tab không được phản chiếu ra health
  response trong khi capability hợp lệ vẫn được giữ lại.

## Bằng chứng kiểm chứng

- Targeted: `uv run pytest tests/test_phase_1_remote_gpu_http.py` — **9 passed**.
- Full suite: `uv run pytest` — **740 passed, 3 skipped, 1 warning**.
- Static: `uv run python -m compileall src tests` và `git diff --check` — **đạt**.
- Live model-service smoke và production parity chưa thể xác minh vì checkout
  chưa có endpoint, credential và catalog production thật.

## Kết luận

Thay đổi giữ nguyên các capability hợp lệ hiện có, đồng thời fail-closed ở
boundary khi payload cố đưa control character vào health contract.
