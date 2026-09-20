# Bằng chứng iteration 163 — kiểm tra HTTP transport contract

## Phạm vi

Siết constructor của `LiteLLMModelClient` theo nguyên tắc fail-fast của kiến trúc
Clean Code: dependency HTTP phải cung cấp `post` callable trước khi request đầu
tiên chạy. Transport thiếu method không được trôi tới lỗi `AttributeError` trong
runtime.

## Thay đổi và kiểm chứng TDD

- Bổ sung regression test cho transport không có `post` và transport có `post`
  nhưng không callable; cả hai đều bị reject bằng `ValueError` rõ ràng.
- Bổ sung guard `http_client.post` trong constructor.
- Cập nhật spy transport của composition-root test để phản ánh contract thật,
  nhưng không thực hiện model I/O.
- Targeted tests: **67 passed, 1 warning**.
- Full suite: **716 passed, 3 skipped, 1 warning**.
- `python -m compileall -q src tests`: thành công.
- `git diff --check`: thành công; chỉ còn warning chuyển đổi LF/CRLF của Git.

## Giới hạn

Đây là kiểm chứng offline bằng fake transport. Live model-service smoke và
production golden parity vẫn chưa xác minh vì checkout chưa có endpoint,
credential và production catalog thật.
