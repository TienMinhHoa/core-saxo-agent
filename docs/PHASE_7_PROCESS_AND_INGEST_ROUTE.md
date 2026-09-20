# Phase 7 — Route extraction đã persist sang ingestion

## Mục tiêu

Khép một lát cắt API nhỏ theo `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: sau khi
extraction đã được xác minh và persist, cùng một request có thể đọc Markdown đã
persist, chunk theo workflow ingestion và upsert vào vector index.

## Thay đổi

- Composition root tạo `IngestExtractedDocument` khi `IndexDocument` được cấu hình.
- Thêm `POST /api/v1/documents/{document_ref}/process-and-ingest`.
- Route giữ ranh giới rõ ràng: gọi `ProcessAndPersistDocument` trước, sau đó gọi
  `IngestExtractedDocument`; response tách thành `extraction` và `ingestion`.
- Route trả `503` nếu persistence hoặc extracted-document ingestion chưa được
  compose, thay vì âm thầm chạy đường tắt.
- Giữ compatibility path `IndexDocument`; paragraph tagger remote chưa được
  compose mặc định nên route này chưa claim live tagging end-to-end.

## Bằng chứng kiểm thử

- Có contract test riêng cho trạng thái composition root không có `VectorIndex`:
  `POST /api/v1/documents/{document_ref}/process-and-ingest` trả `503` với thông báo
  `extracted document ingestion capability is not configured`, thay vì chạy fallback
  hoặc báo indexed giả.

```text
uv run pytest tests/test_phase_7_api_routes.py -q
11 passed, 1 warning

uv run pytest -q
225 passed, 2 skipped, 1 warning

python -m compileall -q src
git diff --check
```

Test mới `test_process_and_ingest_route_runs_persisted_markdown_through_indexing`
chứng minh response có ingestion report `indexed=true`, có một chunk, và vector
index nhận đúng nội dung Markdown sau extraction persistence.

## Giới hạn còn lại

Composition mặc định hiện chỉ tạo `IngestExtractedDocument` từ `IndexDocument`;
để đạt đầy đủ tiêu chí Phase 4, cần tiếp tục compose `TagAndPersistParagraph`
với remote tag generation và conflict-resolution adapters, rồi thêm contract test
cho sidecar/catalog persistence trên route này.
