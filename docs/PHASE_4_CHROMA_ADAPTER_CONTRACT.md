# Evidence Phase 4 — VectorIndex và Chroma adapter

## Phạm vi lát cắt

Iteration 7 chọn phương án **Clean Code** cho một đơn vị nhỏ của Phase 4:
chuẩn hóa projection ghi vào vector index và cô lập Chroma sau một async port.
Lát cắt này chưa nối use case ingestion vào FastAPI và chưa thực hiện gọi Chroma
thật hoặc embedding provider thật.

## Thay đổi đã thực hiện

- `ChunkIndexRecord` mô tả projection searchable với `chunk_id`, document/source
  version, search text, embedding, profile, access scope và metadata.
- `VectorHit` mô tả kết quả search độc lập với SDK.
- `VectorIndex` định nghĩa ba thao tác async: `upsert_chunks`, `delete_chunks` và
  `search`.
- `ChromaVectorIndex` nhận collection đã được composition root tạo sẵn. Các lời
  gọi blocking `upsert`, `delete`, `query` đều chạy qua `anyio.to_thread`, nên
  không chặn FastAPI event loop. Query luôn yêu cầu documents, metadatas và
  distances; metadata hệ thống được bổ sung trước khi upsert.

## Bằng chứng kiểm thử

Lệnh:

```text
.\.venv\Scripts\python.exe -m pytest tests/test_phase_4_ingestion_contract.py -q --basetemp=.pytest-tmp
```

Kết quả: **9 passed**.

Contract test dùng fake Chroma collection để kiểm tra offline:

1. projection vector và metadata được gửi đúng khi upsert;
2. delete truyền đúng chunk IDs;
3. search truyền `include = documents + metadatas + distances`;
4. kết quả SDK được chuyển thành `VectorHit`.

## Giới hạn còn lại

- Chưa có adapter tạo `PersistentClient`/collection từ settings.
- Chưa nối `IngestionCommand` với workflow thực tế và `IngestionReport`.
- Chưa chứng minh persistence hoặc tương thích với một Chroma server thật.
- Chưa triển khai paragraph tagging, remote embedding hay idempotent re-index
  end-to-end.
