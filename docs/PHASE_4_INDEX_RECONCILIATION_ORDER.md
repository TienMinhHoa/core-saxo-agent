# Bằng chứng Phase 4 — thứ tự reconciliation vector index

## Phạm vi

`IndexDocument` phải giữ trạng thái index cũ nguyên vẹn nếu batch upsert thất bại.
Đây là một phần của yêu cầu Phase 4: batch chưa commit không được đánh dấu
`indexed` và không được làm mất dữ liệu đã có.

## Thay đổi

- Đọc danh sách chunk hiện tại trước để xác định stale IDs.
- Thực hiện `upsert_chunks` trước.
- Chỉ gọi `delete_chunks` cho stale IDs sau khi upsert hoàn tất thành công.
- Nếu vector index ném lỗi, báo cáo `indexed=False` và không xóa stale chunks.

## Bằng chứng kiểm thử

- Test hồi quy: `test_index_document_reports_partial_failure_without_claiming_indexed`.
- Test này mô phỏng một stale chunk và lỗi upsert; kết quả xác nhận `deleted_ids == ()`.
- `uv run pytest -q tests/test_phase_4_index_document.py`: **16 passed**.
- `uv run pytest -q`: **261 passed, 2 skipped, 1 warning**.
- `python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.

## Giới hạn

Đây là đảm bảo thứ tự và không phải giao dịch atomic của Chroma. Nếu process chết
giữa upsert và delete, lần chạy ingestion tiếp theo vẫn cần reconciliation để dọn
stale chunks.
