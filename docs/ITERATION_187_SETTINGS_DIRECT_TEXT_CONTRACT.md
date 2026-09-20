# Iteration 187 - Contract chuỗi khi khởi tạo `AppSettings` trực tiếp

## Mục tiêu

Đồng bộ đường biên runtime của `AppSettings` với đường đọc biến môi trường. Trước thay đổi này, gọi trực tiếp `AppSettings(...)` có thể bỏ qua kiểm tra URL, token, model profile và tên collection mà `from_environment(...)` đã thực hiện.

## Thay đổi

- `AppSettings.__post_init__` kiểm tra lại `remote_gpu_base_url` bằng contract HTTPS an toàn.
- Kiểm tra bearer token không rỗng và không chứa ký tự điều khiển trước khi có thể được dùng làm HTTP header.
- Kiểm tra `litellm_endpoint` nếu được cung cấp, cùng `litellm_model_profile` và `chroma_collection_name` khi khởi tạo trực tiếp.
- Giữ nguyên khả năng để trống `litellm_endpoint` trong direct construction nhằm tương thích với default hiện tại; composition root vẫn cung cấp endpoint đầy đủ từ môi trường.

## Bằng chứng kiểm thử

- `uv run pytest -q tests/test_phase_1_settings.py`: **56 passed**.
- Bộ test mới bao phủ HTTP URL, user-info/query trong URL, token rỗng/ký tự điều khiển, endpoint không phải HTTPS, profile rỗng và collection name sai định dạng.
- Full suite, `compileall` và `git diff --check` được chạy sau thay đổi; kết quả ghi ở handoff của iteration này.

## Giới hạn còn lại

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì checkout chưa có endpoint, credential và catalog production được phê duyệt.
