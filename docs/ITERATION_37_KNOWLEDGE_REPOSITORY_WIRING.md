# Iteration 37 — Wiring KnowledgeRepository vào ingestion

## Phạm vi

Iteration này hoàn tất một lát cắt nhỏ của Phase 4 trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: ingestion phải phát hành
full-fidelity chunk metadata sang `KnowledgeRepository`, độc lập với vector
index. Không thay đổi backend storage hay thêm job lifecycle.

## Thay đổi

- `IndexDocument` nhận `KnowledgeRepository` tùy chọn qua dependency injection.
- Mỗi `ChunkIndexRecord` được chuyển thành `KnowledgeChunk` trước khi gọi
  `VectorIndex.upsert_chunks`.
- Mapping giữ `document_id`, `source_version`, `search_text`, heading/page,
  tags, image refs và tạo `content_hash` SHA-256 cùng `knowledge://` source ref.
- Nếu knowledge persistence lỗi, workflow trả `indexed=False` và không gọi
  vector upsert; lỗi được ghi trong `IngestionReport`.
- Không truyền dependency này vẫn giữ compatibility với các caller hiện tại.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_4_ingest_extracted_document.py -q
6 passed

uv run pytest -q
334 passed, 2 skipped, 1 warning

uv run python -m compileall -q src tests
git diff --check
```

Hai test mới kiểm chứng mapping full-fidelity và failure boundary của
knowledge persistence. Hai test skip là dependency/sample có điều kiện của
checkout hiện tại; warning đến từ alias deprecated trong Starlette.

## Giới hạn còn lại

Chưa có live model-service smoke, production catalog parity hoặc deployment
verification vì checkout vẫn không cung cấp endpoint/credential/catalog thật.
Đây là bằng chứng offline cho wiring và contract, không phải xác nhận runtime
production.
