# Iteration 180 - contract clock của health cache

## Phạm vi

Tiếp tục hardening `CachedRemoteGpuGateway` theo mục 17.3 và tiêu chí nghiệm
thu async health trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Iteration này
chỉ xử lý giá trị runtime do dependency `clock` trả về.

## Thay đổi

- `CachedRemoteGpuGateway` đọc clock qua một boundary riêng và fail-closed nếu
  clock trả về kiểu không phải số hoặc số không hữu hạn (`NaN`, `+/-Infinity`).
- Timestamp được chuẩn hóa thành `float` trước khi so sánh TTL và ghi cache,
  tránh phép tính TTL không xác định làm cache bỏ qua hoặc refresh sai.
- Bổ sung test TDD chứng minh cả ba giá trị không hữu hạn đều bị từ chối với
  lỗi contract rõ ràng.

## Bằng chứng kiểm thử offline

- `uv run pytest tests/test_phase_1_remote_gpu_http.py -q`: **15 passed**.
- `uv run pytest -q`: **746 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; Git chỉ cảnh báo line ending CRLF trên Windows.

## Giới hạn xác minh

Live model-service smoke và production golden parity chưa thể thực hiện trong
checkout hiện tại vì thiếu endpoint, credential và production catalog thật.
