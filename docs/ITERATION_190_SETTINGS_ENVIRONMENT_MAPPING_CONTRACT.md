# Iteration 190 — hợp đồng mapping environment của AppSettings

## Phạm vi

Hardening boundary `AppSettings.from_environment`: mọi key và value của
mapping cấu hình phải là chuỗi, giống contract của `os.environ`. Input sai
kiểu phải bị từ chối bằng `SettingsValidationError` trước khi parser con
được gọi.

## Thay đổi

- Thêm `_validate_environment_mapping` tại boundary `from_environment`.
- Từ chối mapping không phải `Mapping`, key không phải chuỗi hoặc value không
  phải chuỗi với thông báo lỗi không chứa dữ liệu bí mật.
- Thêm regression test cho `Path`, `int`, `bool` và `None`; test được viết
  trước implementation để ghi nhận lỗi cũ (có trường hợp `AttributeError`, có
  trường hợp integer được chấp nhận âm thầm).

## Bằng chứng kiểm thử

- Test mục tiêu: `34 passed`.
- Full suite: `787 passed, 3 skipped, 1 warning`.
- Đã chạy thêm `python -m compileall -q src tests` và `git diff --check`.

## Giới hạn xác minh

Đây là kiểm thử offline. Live model-service smoke và production golden parity
vẫn chưa thể xác minh vì checkout chưa có endpoint, credential và catalog
production được cấp quyền.
