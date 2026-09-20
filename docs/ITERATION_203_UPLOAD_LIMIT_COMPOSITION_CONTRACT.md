# Iteration 203 — Contract giới hạn upload tại composition boundary

## Phạm vi

`AppSettings` đã đọc và kiểm tra `SAXO_MAX_UPLOAD_BYTES`, nhưng
`build_capability_router()` vẫn là public boundary có thể được gọi trực tiếp
với giá trị sai. Khi đó lỗi chỉ xuất hiện lúc request upload chạy, làm cấu hình
sai biến thành lỗi runtime khó chẩn đoán.

## Thay đổi

- `build_capability_router()` fail-fast nếu `max_upload_bytes` không phải số
  nguyên dương.
- Boolean bị từ chối riêng vì Python coi `bool` là một subclass của `int`.
- Bổ sung regression tests cho `0`, `-1` và `True` theo TDD.

## Bằng chứng

- Trước implementation: 3 test mới cùng fail vì router chấp nhận cấu hình sai.
- Sau implementation: `uv run pytest tests/test_phase_7_api_routes.py -q
  --basetemp=.pytest-tmp-203` đạt **35 passed, 1 warning**.
- Toàn bộ suite: `uv run pytest -q --basetemp=.pytest-tmp-203-full` đạt
  **886 passed, 3 skipped, 1 warning**.
- `python -m compileall -q src tests` đạt.
- `git diff --check` đạt; warning LF/CRLF là quy ước checkout Windows hiện có.

## Trạng thái acceptance

Đơn vị này củng cố tiêu chí upload có kiểm soát trong yêu cầu artifact: giới
hạn kích thước được kiểm tra ngay tại boundary dựng API, trước khi nhận request.
Live model-service smoke và production golden parity vẫn chưa xác minh vì
checkout chưa có endpoint, credential và catalog production thật.
