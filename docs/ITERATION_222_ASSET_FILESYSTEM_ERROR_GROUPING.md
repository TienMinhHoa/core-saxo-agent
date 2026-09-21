# Iteration 222 - gom nhóm lỗi filesystem của asset endpoint

## Phạm vi

Iteration này thực hiện một refactor nhỏ trong `GET /api/v1/assets/{asset_ref}`.
Bốn lỗi filesystem có cùng semantics HTTP 404 được gom vào một nhánh xử lý:
`FileNotFoundError`, `FileExistsError`, `IsADirectoryError` và
`NotADirectoryError`.

Không thay đổi status code, nội dung response, thứ tự kiểm tra checksum hoặc
quyền truy cập. `PermissionError` vẫn trả 403 và `ValueError` vẫn trả 422.

## Bằng chứng

- Các test API hiện hữu đã bao phủ riêng cả bốn lỗi filesystem và tiếp tục xác
  nhận response `{"detail": "asset not found"}`.
- Refactor chỉ giảm lặp ở exception mapping; không bắt rộng `OSError`, nên các
  lỗi hệ thống ngoài contract không bị che giấu thành 404.
- Live model-service smoke và production parity vẫn chưa thể xác minh vì
  checkout chưa có endpoint, credential và production catalog thật.
