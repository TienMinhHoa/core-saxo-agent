# Iteration 63 — siết contract source row của Chroma

## Phạm vi

Tiếp tục hardening adapter `ChromaSemanticRetriever` theo contract Chroma ở
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: kết quả provider malformed phải
bị từ chối tại boundary, không được âm thầm biến thành evidence thiếu dữ liệu.

## Thay đổi

- `_validated_chroma_rows` yêu cầu mọi `document` là chuỗi.
- `_validated_chroma_rows` yêu cầu mọi `metadata` là mapping.
- Bổ sung regression tests cho document sai kiểu và metadata sai kiểu.

Điều này giữ source text và metadata ở trạng thái rõ ràng trước khi map sang
`ChunkHit`; không còn fallback `{}` hoặc bỏ qua document sai kiểu ở bước map.

## Bằng chứng kiểm chứng

- `uv run pytest tests/test_chroma_semantic_retriever.py -q`: **19 passed**.
- `uv run pytest -q`: **394 passed, 2 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; chỉ còn cảnh báo chuyển dòng LF/CRLF của Git.

## Giới hạn còn lại

Live model-service smoke và production golden parity chưa thể chạy vì checkout
chưa có endpoint, credential và catalog production thật. Vì vậy stop condition
của toàn bộ refactor chưa được đánh dấu hoàn tất.
