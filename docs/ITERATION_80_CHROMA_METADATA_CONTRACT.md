# Iteration 80 - Contract metadata trước Chroma upsert

## Phạm vi

Siết validation tại boundary của `ChromaVectorIndex` theo yêu cầu trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: metadata phải được kiểm tra trước khi
gọi Chroma, không để provider tự phát hiện payload sai sau khi đã bắt đầu I/O.

## Thay đổi

- Reject metadata key không phải chuỗi hoặc chuỗi rỗng/whitespace.
- Reject metadata value là `None`, mapping lồng nhau, bytes/bytearray, hoặc số
  không hữu hạn (`NaN`, `inf`).
- Giữ các scalar `str`, `int`, `float`, `bool` hợp lệ; tuple/list vẫn được
  project đệ quy thành list để bảo toàn contract structured metadata hiện có.
- Khi metadata sai, `upsert_chunks()` fail-closed trước khi gọi
  `collection.upsert()`.

## Bằng chứng kiểm thử

- TDD targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py -k
  "unsupported_metadata or nested_tuple_metadata or chroma_upsert" -q` - **7 passed**.
- Full suite: `uv run pytest -q` - **443 passed, 2 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` - đạt.
- `git diff --check` - không có lỗi whitespace; Git chỉ cảnh báo chuyển LF/CRLF
  theo cấu hình Windows hiện tại.

## Trạng thái còn lại

Live model-service smoke và production golden parity chưa thể xác minh vì
checkout chưa có endpoint, credential và catalog production thật. Lát cắt này
chỉ chứng minh contract offline tại adapter boundary; không suy diễn thành
production readiness.
