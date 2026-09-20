# Bằng chứng TDD Phase 1 - HTTP RemoteGpuGateway (RED)

## Phạm vi iteration 7

Lát cắt này chỉ khóa hợp đồng RED cho adapter HTTP của `RemoteGpuGateway`.
Nó chưa thêm adapter production, không gọi GPU thật, không sửa extraction,
ingestion, retrieval, chat, UI hay Chroma. Đây là bước Clean Code tiếp theo sau
composition root GREEN: transport bị giữ sau port, còn route/use case không biết
`httpx` hay URL cụ thể.

## Hợp đồng đã khóa

- `HttpRemoteGpuGateway` nhận `AppSettings` đã validate và một `httpx.AsyncClient`
  dùng chung do composition root/lifecycle sở hữu; adapter không tạo client cho từng
  lời gọi health.
- `health()` gọi `GET /v1/health` tương đối với base URL đã cấu hình, gửi bearer
  token qua header `Authorization`, và chỉ công nhận ba trạng thái công khai
  `ready`, `degraded`, `unavailable`.
- Lỗi HTTP, lỗi transport/timeout, JSON thiếu `status` hoặc trạng thái không thuộc
  hợp đồng trả về `unavailable`. Vì vậy health không báo sẵn sàng giả khi GPU server
  hoặc wire contract hỏng.
- Test dùng `httpx.MockTransport`; không có mạng thật, GPU, CUDA, Paddle, Chroma
  hay provider nào được gọi.

## Bằng chứng RED offline

Đã chạy tại checkout hiện tại:

```powershell
uv run pytest tests/test_phase_1_remote_gpu_http.py --basetemp=.pytest-tmp -q
```

Kết quả mong đợi và quan sát: collection dừng với
`ImportError: cannot import name 'HttpRemoteGpuGateway' from 'saxophone.platform.remote_gpu'`.
Đây là RED có chủ đích: port/fallback hiện có nhưng adapter HTTP chưa tồn tại.

Regression phần đã GREEN vẫn phải chạy độc lập:

```powershell
uv run pytest --ignore=tests/test_phase_1_remote_gpu_http.py --basetemp=.pytest-tmp -q
uv run python -m compileall -q src tests
git diff --check
```

## Bước tiếp theo

Sau khi duyệt test, thêm tối thiểu `HttpRemoteGpuGateway` sau port hiện có, giữ
client async dùng chung và làm xanh đúng file test này. Timeout/retry, cache
capabilities và submit/poll/cancel là các lát cắt riêng sau khi health adapter
đã có hành vi ổn định.
