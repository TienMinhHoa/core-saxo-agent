# Phase 1 — HTTP Remote GPU Gateway: bằng chứng GREEN

## Phạm vi lát cắt

Hoàn thiện `HttpRemoteGpuGateway` cho đúng contract health đã được khóa RED
trong `tests/test_phase_1_remote_gpu_http.py`. Đây là adapter hạ tầng, không
phải route FastAPI và không khởi chạy workload GPU tại backend.

## Thay đổi thực hiện

- Adapter nhận một `httpx.AsyncClient` dùng chung từ composition root/lifecycle
  ở phase kế tiếp; adapter không tự tạo, đóng hay gọi GPU khi import.
- `health()` gọi cố định `GET {SAXO_REMOTE_GPU_BASE_URL}/v1/health`, gửi bearer
  token qua header `Authorization`, và chỉ công bố `ready`, `degraded` hoặc
  `unavailable`.
- Lỗi mạng, HTTP không thành công, JSON sai kiểu hoặc status ngoài contract đều
  trở thành `unavailable`; response health không mang token, URL hay lỗi nội bộ.
- Khai báo rõ `httpx>=0.28,<1` là dependency production để adapter không dựa
  vào dependency bắc cầu của FastAPI.

## Bằng chứng kiểm chứng offline

Chạy sau khi triển khai:

```powershell
uv lock
uv run pytest tests/test_phase_1_remote_gpu_http.py -q
uv run pytest -q
```

Đã hoàn tất trong iteration này:

```text
4 passed in 0.40s
51 passed, 2 skipped, 1 warning in 2.10s
```

`python -m compileall -q src` và `git diff --check` cũng hoàn tất không lỗi.
Hai skip là Gradio optional chưa cài và sample source không có trong checkout;
warning là deprecation từ Starlette test client. Không có live GPU smoke test
trong lát cắt này; `MockTransport` kiểm tra request và mọi nhánh lỗi một cách
xác định.

## Ranh giới còn lại

Chưa thay default `UnavailableRemoteGpuGateway` trong `create_app`: việc wiring
client dùng chung cần lifecycle FastAPI rõ ràng và test riêng, tránh rò rỉ
connection/client trong lúc chỉ hoàn thiện adapter health.
