# Iteration 193 — chặn control character trong runtime path

## Phạm vi

Sau khi Iteration 192 chặn parent traversal cho path tương đối và tuyệt đối,
boundary cấu hình vẫn cho phép `NUL` và control character đi vào `Path`. Các
giá trị này có thể làm lỗi muộn khi adapter filesystem/Chroma sử dụng path.

## Thay đổi

- Bổ sung `_validate_runtime_path()` để từ chối mọi ký tự ASCII control
  (`U+0000`–`U+001F`, `U+007F`) trong `data_root` và
  `chroma_persist_directory`.
- Áp dụng đồng nhất cho cả `AppSettings(...)` trực tiếp và
  `AppSettings.from_environment(...)`.
- Thêm 4 regression tests TDD cho hai field và hai boundary; lỗi được trả về
  dưới dạng `SettingsValidationError`, không chạm filesystem.

## Bằng chứng

- Trước implementation: 4 test mới **failed**, xác nhận contract bị bỏ lọt.
- Sau implementation: targeted **4 passed**.
- Full suite: **797 passed, 3 skipped, 1 warning**.
- `python -m compileall -q src`: đạt.
- `git diff --check`: đạt; chỉ còn cảnh báo chuyển đổi LF/CRLF của Git trên
  Windows.
- Live model-service smoke và production golden parity vẫn chưa xác minh do
  checkout chưa có endpoint, credential và production catalog thật.

## Quy tắc tổng quát

Mọi filesystem path đi qua boundary cấu hình phải được kiểm tra cả cấu trúc
path (parent traversal) và nội dung ký tự nguy hiểm trước khi được truyền cho
adapter; không dựa vào type hint hoặc đợi filesystem báo lỗi.
