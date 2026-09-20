# Iteration 158 - Siết payload JSON tại model boundary

## Phạm vi

Hoàn thiện một contract nhỏ trong mục 12.5 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
`ModelRequest.input` và `ModelRequest.metadata` phải chứa giá trị có thể vận
chuyển bằng JSON trước khi adapter gọi model service.

## Thay đổi

- Bổ sung kiểm tra đệ quy cho mapping lồng nhau, list/tuple và scalar JSON trong
  request envelope.
- Từ chối key lồng nhau không phải chuỗi, set/bytes/object tùy ý và số thực
  `NaN`/`Infinity` bằng `ModelValidationError`.
- Giữ nguyên mapping proxy ở lớp ngoài; `ModelResponse.output` vẫn cho phép DTO
  typed như `ArtifactRef` để không phá vỡ task-specific adapter mapping.

## Bằng chứng xác minh

- `uv run pytest tests/test_phase_1_model_client_contract.py -q`: **26 passed**.
- `uv run pytest -q --basetemp=.pytest-tmp`: **690 passed, 3 skipped, 1 warning**.
- `python -m compileall -q src`: đạt.
- `git diff --check`: đạt; chỉ còn cảnh báo line ending CRLF tự nhiên của
  checkout Windows.
- Live model-service smoke và production golden parity chưa xác minh vì checkout
  chưa có endpoint, credential và catalog production thật.

## Kết luận

Model request boundary fail-fast với payload không phải JSON, tránh để lỗi
serialization phát sinh muộn trong HTTP transport; response output vẫn bảo toàn
contract typed của application adapter.
