# Iteration 191 — đồng bộ contract path giữa direct settings và environment

## Phạm vi

`AppSettings.from_environment` đã từ chối path tương đối có thành phần `..`,
nhưng khởi tạo `AppSettings` trực tiếp vẫn có thể nhận `Path("../outside")`.
Khoảng hở này làm hai composition boundary có hành vi khác nhau và không phù
hợp với nguyên tắc safe path trong kế hoạch kiến trúc.

## Thay đổi

- Mở rộng `_validate_runtime_path` để từ chối parent traversal trên path tương
  đối cho cả `data_root` và `chroma_persist_directory`.
- Bổ sung regression test TDD cho cả hai field; lỗi luôn là
  `SettingsValidationError` và không chạm filesystem.

## Bằng chứng kiểm thử

- Test mới ban đầu fail với **2 failed**, chứng minh khoảng hở tồn tại.
- Targeted settings test: **30 passed, 41 deselected**.
- Full suite: **789 passed, 3 skipped, 1 warning**; `compileall` và
  `git diff --check` đều hoàn tất thành công (chỉ có cảnh báo line-ending của
  Git trên Windows).
- Live model-service smoke và production golden parity chưa thể xác minh vì
  checkout chưa có endpoint, credential và catalog production.
