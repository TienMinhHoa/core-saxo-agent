# Iteration 217 - chuẩn hóa lỗi quyền truy cập asset

## Phạm vi

Lát cắt này hoàn thiện error mapping của `GET /api/v1/assets/{asset_ref}` theo
nhóm lỗi `access/asset path error` trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.
Khi artifact repository từ chối đọc bằng `PermissionError`, API không để lỗi
thoát thành HTTP 500 mà trả lỗi HTTP 403, không làm lộ chi tiết filesystem.

## Thay đổi

- Bổ sung regression test ở `tests/test_phase_7_api_routes.py` với repository
  giả lập bị từ chối quyền đọc.
- Bổ sung mapping `PermissionError -> 403 asset access denied` tại asset route;
  giữ nguyên mapping `FileNotFoundError -> 404` và lỗi contract/checksum
  `ValueError -> 422`.

## Bằng chứng kiểm thử

- Red trước implementation: test permission mới thất bại vì
  `PermissionError` thoát khỏi route.
- Green targeted:
  `uv run pytest tests/test_phase_7_api_routes.py -k asset_route -q
  --basetemp=.pytest-tmp-217-green` -> **8 passed, 1 warning**.

Full suite và kiểm tra tĩnh được chạy sau khi hoàn tất thay đổi; kết quả cuối
cùng được ghi ở `docs/REFACTOR_ACCEPTANCE_STATUS.md`.

## Giới hạn còn lại

Live model-service smoke và production golden parity vẫn chưa xác minh vì
checkout chưa có endpoint, credential và production catalog thật.
