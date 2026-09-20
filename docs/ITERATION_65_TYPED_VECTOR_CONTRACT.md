# Bằng chứng Iteration 65 — hợp đồng vector embedding hữu hạn và đúng kiểu

## Phạm vi

Siết boundary ingestion trước khi dữ liệu đi vào Chroma. Python coi `bool` là
`int`, nên `math.isfinite(True)` không đủ để loại một vector sai kiểu.

## Thay đổi

- `EmbeddingRecord.vector` chỉ nhận các giá trị `int`/`float` hữu hạn và loại
  riêng `bool`.
- `ChunkIndexRecord.embedding` áp dụng cùng hợp đồng trước bước Chroma upsert.
- Bổ sung regression tests cho hai boundary khi vector chứa `True`.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_4_ingestion_contract.py -q`: **24 passed**.
- `uv run pytest -q`: **401 passed, 2 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; chỉ còn cảnh báo chuyển đổi LF/CRLF của Git trên
  hai file Python đã sửa.
- `uv run ruff check ...`: không chạy được vì executable `ruff` không có trong
  môi trường (`Failed to spawn: ruff`).

## Trạng thái còn lại

Đây là bằng chứng offline. Live model-service smoke và production golden parity
vẫn chưa xác minh vì checkout chưa có endpoint, credential và catalog production
thật.
