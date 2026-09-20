# Evidence Phase 4 — Đồng nhất kích thước embedding

## Phạm vi

Khóa một invariant trước khi `IndexDocument` ghi cache hoặc đẩy dữ liệu vào
vector index: mọi embedding trong cùng một batch phải có cùng số chiều. Chroma
không thể tìm kiếm ổn định nếu một collection nhận các vector khác chiều, vì vậy
đây là validation thuộc application boundary, không giao cho adapter xử lý trễ.

## Thay đổi

- `IndexDocument._embed_records` kiểm tra `dimension` của toàn bộ record đã
  resolve, bao gồm cả record mới và record lấy từ reuse store.
- Batch không đồng nhất trả về `IngestionReport(indexed=False)` với lỗi rõ ràng
  `embedding dimensions must match`.
- Validation chạy trước khi lưu embedding mới vào reuse store và trước khi gọi
  `VectorIndex.upsert_chunks`, tránh lưu trạng thái không thể sử dụng.
- Bổ sung contract test cho batch gồm vector 2 chiều và 3 chiều.

## Bằng chứng kiểm thử

- Red test trước implementation: test mới thất bại vì batch không đồng nhất vẫn
  được đánh dấu `indexed=True`.
- Sau implementation: `tests/test_phase_4_index_document.py` pass `16 passed`.
- Full suite và compile/diff checks được chạy sau khi hoàn tất iteration; kết quả
  thực tế: `uv run pytest -q` pass `261 passed, 2 skipped, 1 warning`; hai skip
  là do thiếu Gradio và sample source, không phải regression. `compileall` và
  `git diff --check` cũng pass.

## Giới hạn xác minh

Đây là kiểm thử offline với fake embedding provider và fake vector index. Chưa
phải live smoke test với model service hoặc Chroma server thật.
