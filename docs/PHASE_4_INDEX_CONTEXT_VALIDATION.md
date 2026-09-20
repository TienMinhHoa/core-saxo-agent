# Phase 4 — Kiểm tra context trước khi index

## Phạm vi

Iteration 33 siết boundary của `IndexDocument` trước lời gọi `VectorIndex`.
Mỗi `ChunkIndexRecord` phải cùng `document_ref`, `source_version`,
`embedding_profile` và `access_scope` với `IngestionCommand`.

Mục tiêu là không trộn vector của model/profile khác hoặc dữ liệu khác tenant
vào cùng một lần upsert. Đây là kiểm tra application-level; adapter Chroma
vẫn chịu trách nhiệm mapping và persistence của vector index.

## Thay đổi

- Bổ sung validation `embedding_profile` trước `upsert_chunks`.
- Bổ sung validation `access_scope` trước `upsert_chunks`.
- Bổ sung contract test cho cả hai lỗi và xác nhận vector index không bị gọi.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_4_index_document.py`: 5 passed.
- `uv run pytest`: sẽ được chạy sau khi hoàn tất lát cắt iteration này.

## Giới hạn còn lại

Iteration này chưa triển khai embedding provider, paragraph tagging,
re-index/idempotency hoặc wiring ingestion vào route document. Các phần đó cần
giữ ở các lát cắt riêng để không làm mờ boundary của contract hiện tại.
