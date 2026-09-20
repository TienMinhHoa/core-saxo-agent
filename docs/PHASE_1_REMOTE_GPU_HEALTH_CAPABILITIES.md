# Phase 1 — Capability health của remote GPU

## Phạm vi lát cắt

Lát cắt này hoàn thiện phần `health/capability check` của remote model service
trong mục 12.5 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Backend chỉ công
bố `status` và danh sách capability dạng tên; không công bố URL, bearer token,
local path hay toàn bộ payload từ máy GPU.

## Thay đổi

- `RemoteGpuHealth` có thêm `capabilities: tuple[str, ...]` bất biến.
- `HttpRemoteGpuGateway` đọc capability hợp lệ, trim khoảng trắng, loại phần tử
  sai kiểu và loại trùng; lỗi HTTP/transport/schema vẫn trả về trạng thái an toàn
  `unavailable` với capability rỗng.
- `GET /api/v1/health` trả thêm `remote_gpu_capabilities` để readiness có thể
  phân biệt remote service sẵn sàng cho task nào, trong khi các capability ứng
  dụng chưa được wiring vẫn giữ trạng thái `disabled`.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_1_remote_gpu_http.py tests/test_phase_1_composition_root.py
```

Các contract test kiểm tra auth/path dùng chung HTTP client, status hợp lệ,
fallback an toàn, lọc capability malformed/trùng và projection qua health API.
