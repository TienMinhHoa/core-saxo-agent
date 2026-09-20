# Bằng chứng Phase 4: chunking Markdown deterministic

## Phạm vi lát cắt

Iteration 39 bổ sung boundary thuần cho bước `normalize source blocks -> build
hierarchy/chunks` trong kế hoạch refactor. Hàm `build_source_chunks` nhận
Markdown đã extract và trả về `IngestionSourceChunk` trước embedding.

## Quy tắc đã mã hóa

- Chỉ heading ở `heading_level` được chọn mở chunk; heading lồng nhau được giữ
  trong source text để không làm mất provenance.
- Dòng `## Page N` chỉ cập nhật `page_start/page_end`, không trở thành nội dung.
- Chunk rỗng bị bỏ qua; nội dung và dấu phân cách được normalize deterministically.
- `chunk_id` ổn định theo document, source version, thứ tự và nội dung; không có
  LLM, provider hay embedding trong boundary này.
- Metadata và scope được đóng gói qua `IngestionSourceChunk`, sẵn sàng cho bước
  tagging/embedding tiếp theo.

## Bằng chứng kiểm thử

- `uv run pytest -q tests/test_phase_4_markdown_chunking.py`: 4 passed.
- Test bao phủ nội dung heading/nested heading, page provenance, bỏ chunk rỗng,
  tính deterministic, scope binding và heading level không hợp lệ.

## Giới hạn còn lại

Lát cắt này chưa đọc `PdfExtractionResult.manifest` từ `ArtifactRepository`,
chưa nối chunker vào route ingest, và chưa thực hiện tagging hoặc embedding.
Đó là các bước riêng để giữ dependency boundary và khả năng kiểm chứng rõ ràng.
