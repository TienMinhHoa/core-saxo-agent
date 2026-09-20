# Iteration 92 — Bắt buộc identity trong metadata kết quả Chroma

## Phạm vi

Theo contract source-first trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, mỗi
record Chroma phải mang `chunk_id` trong metadata để kết quả search giữ được
identity độc lập với provider. Lát thay đổi này chỉ siết boundary đọc kết quả
`ChromaVectorIndex`; không thay đổi API retrieval hoặc cách tính score.

## Thay đổi

- Fixture search hợp lệ hiện khai báo `metadata.chunk_id` đúng với row ID.
- Thêm regression test chứng minh metadata thiếu `chunk_id` bị từ chối trước khi
  tạo `VectorHit`.
- Adapter fail-closed với metadata `chunk_id` thiếu, rỗng hoặc không phải chuỗi;
  identity khác row ID tiếp tục bị từ chối.

## Kiểm chứng

- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py`.
- Full suite: `uv run pytest`.
- Tĩnh: `uv run python -m compileall src tests` và `git diff --check`.
- Live model-service smoke và production parity chưa chạy vì checkout chưa có
  endpoint, credential và catalog production được phê duyệt.
