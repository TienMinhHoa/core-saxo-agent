# Iteration 178 — fail-fast dependency ports cho remote health cache

## Phạm vi

Tiếp tục hardening `CachedRemoteGpuGateway` theo lựa chọn Clean Code. Cache
không nên nhận dependency sai hình dạng rồi chỉ phát hiện lỗi ở lần gọi health
đầu tiên. Vì vậy constructor hiện kiểm tra sớm hai port runtime được inject:

- `gateway.health` phải là callable;
- `clock` phải là callable.

TTL finite/positive và single-flight refresh của các iteration trước vẫn được
giữ nguyên.

## TDD và bằng chứng

Đã thêm hai regression test trước khi sửa implementation:

- gateway có `health = None` bị từ chối với `TypeError` ổn định;
- clock không callable bị từ chối với `TypeError` ổn định.

Lần chạy test trước implementation tái hiện đúng hai lỗi mới, sau đó
implementation được bổ sung để làm test xanh.

## Kiểm tra sau thay đổi

- `uv run pytest tests/test_phase_1_remote_gpu_http.py -q`: **13 passed**.
- `uv run pytest`: **744 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.

Đây là kiểm chứng offline. Live model-service smoke và production golden
parity vẫn chưa xác minh vì checkout chưa có endpoint, credential và catalog
production thật.

## Tác động kiến trúc

Health cache tiếp tục là adapter ở platform boundary, không tạo job lifecycle,
không gọi GPU local, và không làm thay đổi public status contract
`ready/degraded/unavailable`.
