# Iteration 181 — Timeout health gateway hữu hạn

## Phạm vi

Siết hợp đồng `HttpRemoteGpuGateway` theo yêu cầu kiến trúc: timeout của
health request phải là số dương hữu hạn trước khi adapter tạo request HTTP.

## Thay đổi

- `HttpRemoteGpuGateway` từ chối `NaN`, `+infinity` và `-infinity` bằng
  `ValueError` với thông báo ổn định.
- Bổ sung regression test cho cả ba giá trị không hữu hạn.

## Bằng chứng kiểm thử

- Test đỏ trước khi sửa: test mới thất bại vì constructor cũ chấp nhận giá trị
  không hữu hạn.
- Test xanh sau khi sửa: `uv run pytest -q tests/test_phase_1_remote_gpu_http.py`
  — 16 passed.
- Full suite: `uv run pytest -q` — 747 passed, 3 skipped, 1 warning.
- `uv run python -m compileall -q src tests` và `git diff --check` — đạt.

## Giới hạn bằng chứng

Đây là kiểm thử offline với HTTP mock; chưa phải live smoke tới model service
hoặc production golden parity vì checkout chưa có endpoint, credential và
catalog production được phê duyệt.
