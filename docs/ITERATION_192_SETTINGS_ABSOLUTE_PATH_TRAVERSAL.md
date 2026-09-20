# Iteration 192 — chặn parent traversal trong path tuyệt đối

## Phạm vi

Iteration 191 đã bảo vệ `data_root` và `chroma_persist_directory` khi path tương đối chứa `..`. Rà soát tiếp cho thấy path tuyệt đối như `C:/safe/../outside` vẫn đi qua validator direct construction, dù vẫn chứa component parent traversal.

## Thay đổi

- Bổ sung test TDD cho cả hai field ở hai boundary: `AppSettings.from_environment` và khởi tạo `AppSettings` trực tiếp.
- `_parse_data_root`, `_parse_chroma_directory` và `_validate_runtime_path` nay từ chối mọi path có component `..`, không phụ thuộc path tương đối hay tuyệt đối.
- Validation vẫn fail-closed bằng `SettingsValidationError` và không chạm filesystem.

## Bằng chứng

- Test mới trước implementation: **4 failed**, xác nhận bypass tồn tại cho hai field ở hai boundary.
- Settings suite sau implementation: **75 passed**.
- Full suite: **793 passed, 3 skipped, 1 warning**.
- `python -m compileall -q src` và `git diff --check`: đạt.
- Live model-service smoke và production golden parity vẫn chưa xác minh vì checkout thiếu endpoint, credential và catalog production thật.

## Hậu kiểm

Nguyên nhân lọt lỗi là điều kiện cũ chỉ kiểm tra `..` khi `Path.is_absolute()` là `False`; test trước đó chỉ bao phủ path tương đối. Quy tắc tổng quát: mọi boundary nhận path phải kiểm tra component nguy hiểm trước khi chuẩn hóa hoặc truy cập filesystem, bất kể path có phải absolute hay không.
