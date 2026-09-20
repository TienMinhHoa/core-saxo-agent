# Iteration 102 — Khóa asset API và resolver metadata

## Phạm vi

Kế hoạch kiến trúc yêu cầu target contract `GET /api/v1/assets/{asset_ref}`.
Trước iteration này, backend đã có cổng lưu artifact và image gate cho chat nhưng
chưa có inbound route để phân giải image reference, đọc bytes đã kiểm chứng và
trả media type cho client.

## Thay đổi

- Thêm `ImageArtifactResolver` vào composition root dưới dạng dependency rõ ràng;
  route không tự suy đoán version, checksum hoặc đường dẫn filesystem từ URL.
- Thêm `GET /api/v1/assets/{asset_ref:path}` trong FastAPI inbound adapter.
- Route yêu cầu cả resolver và `ArtifactRepository`, chỉ trả artifact có kind
  `IMAGE`, đọc bytes qua repository (repository tự kiểm tra checksum/size) và trả
  `media_type` đã được khai báo.
- Khóa lỗi boundary: capability chưa được compose trả `503`, artifact không phải
  image trả `422`, artifact không tồn tại trả `404`.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_7_api_routes.py -q
25 passed, 1 warning

uv run python -m compileall -q src tests
git diff --check
```

Các test mới xác minh đường đi thành công, capability chưa được cấu hình và
resolver trả artifact không phải image. Đây là bằng chứng offline/contract; live
model-service smoke và production deployment vẫn chưa được xác minh trong
checkout này.
