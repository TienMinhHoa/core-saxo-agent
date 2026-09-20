# Bằng chứng iteration 50: API ingestion giữ boundary trước embedding

## Phạm vi

`POST /api/v1/documents/{document_ref}/ingest` hiện nhận các record nguồn chưa có
vector. Route tạo `IndexInputRecord` rồi gọi `IndexDocument`; `EmbeddingProvider`
mới là nơi tạo vector và `VectorIndex` chỉ nhận projection sau embedding.

Điều này loại bỏ việc inbound API dựng `ChunkIndexRecord` (DTO chỉ hợp lệ sau khi
embedding đã được validate), đồng thời ngăn client gửi vector giả hoặc stale vào
application workflow.

## Thay đổi đã xác minh

- Xóa trường `embedding` khỏi `IngestionChunkRequest`.
- Route chuyển từng request record thành `IndexInputRecord`.
- Test route xác nhận provider nhận đúng `(chunk_id, search_text)` và vector được
  tạo trước khi record được upsert vào fake vector index.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_7_api_routes.py -q
9 passed, 1 warning
```

Giới hạn: đây là kiểm thử offline với fake provider/index; chưa xác minh live model
service hoặc Chroma server.
