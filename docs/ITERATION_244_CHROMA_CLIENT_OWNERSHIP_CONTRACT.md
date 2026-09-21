# Iteration 244 - contract ownership client Chroma

## Mục tiêu

Khóa một lỗi cấu hình nhỏ tại boundary của `ChromaVectorIndex`: nếu composition
root truyền `client`, adapter phải có khả năng đóng client đó. Nếu không, lỗi cần
được phát hiện ngay khi khởi tạo thay vì đến shutdown mới trở thành cleanup
không có tác dụng.

## Thay đổi

- `ChromaVectorIndex` fail-fast với `TypeError` khi `client.close` không callable.
- Bổ sung regression test chứng minh dependency sai bị từ chối trước lifecycle
  cleanup.
- Giữ nguyên compatibility của các caller không truyền `client`; các test
  cleanup hiện có vẫn dùng client có `close()` callable.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py -q`
- Full suite: `uv run pytest -q`
- Static: `uv run python -m compileall -q src tests`
- Hygiene: `git diff --check`

Kết quả thực tế:

- Targeted: **101 passed**.
- Full suite: **927 passed, 18 skipped, 1 warning**.
- `compileall`: thành công.
- `git diff --check`: thành công.

Các test skip do Windows không cho tài khoản hiện tại tạo symbolic link,
Gradio hoặc fixture/sample không có trong môi trường; không phải regression của
thay đổi này.

Kết quả thực tế sẽ được ghi sau khi chạy các lệnh trên trong iteration này.

## Trạng thái còn lại

Live model-service smoke và production parity vẫn chưa thể xác minh vì checkout
chưa có endpoint, credential và production catalog thật.
