# Phase 4 — Nối extraction Markdown với paragraph tagging

## Mục tiêu

Đưa workflow `IngestExtractedDocument` tiến thêm một lát cắt theo kiến trúc
Clean Code trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: Markdown đã persist
được chunk và parse thành paragraph, sau đó đi qua boundary tagging/persistence
trước khi embedding và upsert vào vector index.

## Thay đổi

- `IngestExtractedDocument` nhận thêm `IngestDocument` tùy chọn.
- Khi dùng coordinator mới, workflow gọi `parse_chunk_paragraphs` cho từng
  `IngestionSourceChunk`, tạo `IngestionCommand` với `tagging_profile`, rồi
  chuyển chunks và paragraphs sang `IngestDocument`.
- `IngestDocument` tiếp tục sở hữu orchestration
  `tag -> persist sidecar/catalog -> project tags -> embed -> index`.
- Đường tương thích cũ nhận `IndexDocument` vẫn được giữ nguyên để không làm
  vỡ các caller hiện tại trong khi composition root chưa chuyển toàn bộ.

## Bằng chứng kiểm thử

Đã chạy trong repository:

```text
uv run pytest tests/test_phase_4_ingest_extracted_document.py -q
3 passed

uv run pytest -q
224 passed, 2 skipped, 1 warning

python -m compileall -q src
git diff --check
```

Test mới chứng minh tag được tạo trước index và xuất hiện trong metadata của
record vector (`("music",)`). Hai test skip là dependency/sample source đã được
ghi nhận từ baseline, không phải regression của lát cắt này.

## Giới hạn còn lại

Composition root/API hiện vẫn compose `IndexDocument` trực tiếp khi có vector
index override; chưa thể tuyên bố upload/process API đã chạy trọn
`extract -> paragraph -> tag -> embed -> index` với remote provider thật.
