# Phase 7 — Bảo vệ kích thước upload nguồn

## Phạm vi

Lát cắt này hoàn thiện một yêu cầu bảo mật trong kế hoạch kiến trúc: API upload
nguồn phải kiểm tra cả media type và kích thước. Route không còn đọc toàn bộ
payload không giới hạn vào bộ nhớ; giới hạn được khai báo trong `AppSettings`
qua biến `SAXO_MAX_UPLOAD_BYTES`.

## Thay đổi

- Giá trị mặc định là `200 MiB`, tương thích với giới hạn upload cũ của entrypoint
  legacy.
- Giá trị cấu hình phải là số nguyên dương; cấu hình sai bị từ chối ngay khi
  tạo settings.
- Adapter FastAPI đọc theo từng chunk và dừng với HTTP `413` khi vượt giới hạn.
- Artifact repository không được gọi khi payload vượt giới hạn.
- Composition root truyền giới hạn typed từ settings xuống inbound adapter; route
  không tự đọc environment.

## Bằng chứng kiểm tra

Đã chạy offline:

```text
uv run pytest tests/test_phase_1_settings.py tests/test_phase_7_api_routes.py -q
45 passed, 1 warning
```

Test bao phủ default/explicit/invalid settings, upload PDF hợp lệ, media type
không hợp lệ và payload vượt giới hạn. Chưa có live provider smoke test trong
lát cắt này; giới hạn upload được kiểm chứng bằng FastAPI `TestClient` và fake
artifact repository.
