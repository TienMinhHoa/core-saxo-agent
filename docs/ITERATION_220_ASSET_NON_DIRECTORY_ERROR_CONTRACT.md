# Iteration 220 — asset route xử lý path component không phải thư mục

## Mục tiêu

Hoàn thiện error contract của `GET /api/v1/assets/{asset_ref}` cho trường hợp
filesystem báo `NotADirectoryError`: một component trung gian của artifact path
là file thay vì directory. Đây là lỗi identity/path không tìm thấy, không phải
lỗi permission hay lỗi checksum.

## Thay đổi

- Bổ sung regression test tại `tests/test_phase_7_api_routes.py`.
- Route map `NotADirectoryError` thành HTTP `404` với detail `asset not found`.
- Không bắt rộng `OSError`, để lỗi storage ngoài dự kiến vẫn không bị che thành
  một response “not found”.

## Bằng chứng

- TDD red trước khi sửa route: test mới thất bại với `NotADirectoryError` thoát
  ra khỏi ASGI handler.
- Targeted asset route: `11 passed, 29 deselected, 1 warning`.
- Full suite, `compileall` và `git diff --check` được chạy sau thay đổi; kết quả
  được ghi nhận trong handoff của iteration.

## Giới hạn xác minh

Live model-service smoke và production parity vẫn chưa thể chạy vì checkout
chưa có endpoint, credential và production catalog thật.
