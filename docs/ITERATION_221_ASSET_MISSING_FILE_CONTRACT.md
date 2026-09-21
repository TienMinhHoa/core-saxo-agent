# Iteration 221 — hợp đồng asset thiếu file

## Phạm vi

Khóa regression contract cho trường hợp artifact repository không tìm thấy file
ảnh. Đây là lát cắt nhỏ của yêu cầu API `GET /api/v1/assets/{asset_ref}` trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: lỗi storage không được lộ thành HTTP
500 không có chủ đích.

## Thay đổi

- Thêm test TDD `test_asset_route_maps_missing_artifact_to_not_found`.
- Xác minh mapping đã có tại asset route: `FileNotFoundError` trở thành HTTP
  `404` với detail ổn định `asset not found`.
- Không mở rộng bắt lỗi `OSError` tổng quát; các lỗi filesystem khác chỉ được
  ánh xạ khi đã có contract cụ thể.

## Bằng chứng kiểm thử

- Targeted asset route: **41 passed, 1 warning**.
- Full offline suite: **909 passed, 3 skipped, 1 warning**.
- `compileall` và `git diff --check`: chạy sau khi cập nhật test và tài liệu.
- Live model-service smoke và production parity vẫn chưa thể xác minh vì
  checkout không có endpoint, credential và production catalog thật.
