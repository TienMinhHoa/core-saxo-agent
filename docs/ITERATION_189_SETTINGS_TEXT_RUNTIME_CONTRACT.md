# Iteration 189 - hợp đồng runtime cho text của AppSettings

## Phạm vi

Tiếp tục Phase 1 của kế hoạch refactor: `AppSettings` phải trả về
`SettingsValidationError` ổn định khi được khởi tạo trực tiếp với giá trị sai
kiểu. Iteration này khóa các trường URL, bearer token, model profile và tên
collection; trước đó các parser có thể ném `AttributeError` do gọi `.strip()`
trên giá trị không phải chuỗi.

## Thay đổi

- Bổ sung guard kiểu text dùng chung cho các parser settings.
- Giữ nguyên quy tắc validation hiện tại cho giá trị rỗng, URL không an toàn,
  token có control character, profile rỗng và collection name sai định dạng.
- Thêm 5 regression cases cho direct construction với giá trị integer.

## Bằng chứng kiểm chứng

- Test settings: **41 passed** cho targeted selection.
- Full suite: **782 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.

## Trạng thái còn lại

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout chưa có endpoint, credential và catalog production được cấp phép.
