# Hợp đồng ingestion Phase 4

## Phạm vi iteration 6

Iteration này chọn lát cắt Clean Code nhỏ nhất của Phase 4: chuẩn hóa DTO đầu
vào ingestion, embedding record và báo cáo kết quả; đồng thời đặt `VectorIndex`
làm port để use case không phụ thuộc trực tiếp vào Chroma SDK.

## Kết quả

- `IngestionCommand` giữ document/source version, các profile chunk/tag/embed/index
  và access scope; không nhận CLI, HTTP hay path filesystem.
- `EmbeddingRecord` bắt buộc chunk identity, source version, model profile và vector
  hữu hạn, không rỗng; dimension được suy ra từ vector.
- `IngestionReport` ghi counters cho chunk/paragraph/tag/embed/reuse/skip, index
  version, warning/error; không cho phép đánh dấu indexed khi còn paragraph lỗi
  hoặc error.
- `VectorIndex` là async application port với `upsert` theo batch và `delete` theo
  chunk ID. Adapter Chroma sẽ được triển khai ở lát cắt kế tiếp.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_4_ingestion_contract.py -q
5 passed
uv run pytest -q
85 passed, 2 skipped, 1 warning
```

Các test bao phủ command profile, vector hữu hạn/không rỗng, report hoàn tất và
report partial failure. Chưa có kết luận về Chroma thật, remote embedding hoặc
workflow end-to-end; đó là phạm vi integration/live smoke của các iteration sau.
