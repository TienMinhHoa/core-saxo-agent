# Phase 4 — Use case IndexDocument

## Mục tiêu

Iteration 30 chọn lát cắt Clean Code nhỏ nhất của Phase 4: đưa các
`ChunkIndexRecord` đã được chuẩn hóa qua port `VectorIndex`, không để
application layer biết Chroma hay SDK cụ thể.

## Thay đổi

- Thêm `IndexDocument` tại `saxophone.ingestion.use_cases`.
- Kiểm tra mọi record cùng `document_ref` và `source_version` với command trước
  khi gọi index.
- Trả `IngestionReport` có `indexed=False` và lỗi rõ ràng khi vector index thất
  bại; không báo cáo thành công giả.
- Đếm chunk/paragraph/tag để chuẩn bị cho pipeline normalize/tag/embed đầy đủ.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_4_index_document.py`: 3 passed.
- Full suite và `compileall` cần chạy sau khi lát cắt tiếp theo nối workflow
  ingestion vào composition root.

## Giới hạn còn lại

Use case này chưa load extraction manifest, chưa gọi embedding/tagging provider
và chưa được expose thành route. Đây là chủ ý để giữ ranh giới từng bước; việc
persist output extraction vẫn cần chốt contract payload/transfer vì
`PdfExtractionResult` hiện chỉ mang `ArtifactRef`, không mang bytes.
