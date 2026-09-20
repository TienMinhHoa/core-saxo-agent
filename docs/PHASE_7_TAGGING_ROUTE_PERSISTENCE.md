# Phase 7 — Bằng chứng persistence tagging trên route process-and-ingest

## Mục tiêu

Bổ sung contract test cho lát cắt ingestion đầy đủ trong kiến trúc Clean Code:
route `process-and-ingest` đọc Markdown đã persist, chạy tagging qua các port,
sau đó ghi đồng thời tagged-paragraph sidecar và tag catalog độc lập với vector
index.

## Thay đổi

- Thêm fake `TagGenerator` và `TagConflictResolver` để test route không phụ
  thuộc model service thật.
- Dùng `JsonTaggedParagraphRepository` và `JsonTagCatalogRepository` với
  `SAXO_DATA_ROOT` tạm thời để chứng minh persistence thật của hai projection.
- Gửi `tagging_profile=tags-v1` và `resolution_profile=resolve-v1`; kiểm tra
  report có một paragraph được tag, catalog có `Harmony definition`, và đúng
  một sidecar JSON giữ tag đã resolve.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_7_api_routes.py::test_process_and_ingest_route_persists_tagged_paragraph_and_catalog -q
1 passed, 1 warning
```

Test này chứng minh composition hiện tại nối được route → extraction
persistence → `IngestExtractedDocument` → `IngestDocument` →
`TagAndPersistParagraph` → hai repository JSON → vector indexing. Model service
thật và Chroma thật vẫn nằm ngoài phạm vi offline test.

## Giới hạn còn lại

Chưa có live smoke test với LiteLLM/model service, cũng chưa kiểm chứng đồng bộ
sidecar/catalog trên filesystem phân tán. Đây là giới hạn môi trường, không phải
lý do để route giả nhận đã hoàn tất live tagging.
