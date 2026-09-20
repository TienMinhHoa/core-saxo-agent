# Phase 4 — reconcile vector index

## Mục tiêu

Hoàn thiện bước `reconcile vector index` trong ingestion theo
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Trước thay đổi này,
`IndexDocument` chỉ upsert các chunk hiện tại nên chunk cũ của cùng document có
thể vẫn xuất hiện trong kết quả tìm kiếm sau khi nguồn bị rút gọn.

## Thay đổi

- Bổ sung `VectorIndex.list_chunk_ids(document_ref)` vào application port.
- `ChromaVectorIndex` đọc danh sách ID bằng metadata `document_ref`; lời gọi SDK
  blocking vẫn chạy qua `anyio.to_thread`.
- `IndexDocument` tính tập ID hiện tại sau khi embedding đã hợp lệ, xóa các ID
  stale rồi mới upsert projection mới.
- Compatibility fake không có method liệt kê vẫn được phép chạy; adapter thật
  triển khai đầy đủ contract mới.

## Bằng chứng kiểm thử

- `test_index_document_reconciles_stale_chunks_for_document`: stale ID bị xóa,
  chunk hiện tại được giữ lại.
- Nhóm ingestion contract: `31 passed`.
- Toàn bộ suite: `238 passed, 2 skipped, 1 warning`.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; cảnh báo còn lại chỉ là quy đổi LF/CRLF của Git trên
  Windows.

## Ranh giới

Chưa thực hiện live smoke với Chroma server thật; việc kiểm chứng lần này là
offline contract/integration test. Reconciliation chỉ xóa ID được trả về cho
đúng `document_ref`, không xóa dữ liệu của document khác.
