# Iteration 88 - Đồng bộ `chunk_id` giữa Chroma row và metadata

## Phạm vi

Khóa một khoảng hở trong contract kết quả của `ChromaVectorIndex.search`: nếu
provider trả metadata có `chunk_id`, giá trị đó phải trùng với ID canonical của
row. Metadata lệch hoặc chỉ chứa whitespace không được đi tiếp thành `VectorHit`.

## Thay đổi

- Bổ sung validation sau khi kiểm tra shape và kiểu metadata của Chroma.
- Từ chối kết quả có `metadata.chunk_id` khác `ids` tương ứng hoặc không hợp lệ.
- Giữ tương thích với collection cũ không có trường `chunk_id` trong metadata;
  adapter vẫn dùng ID của row làm identity canonical.
- Bổ sung regression test TDD cho metadata trỏ sang chunk khác và metadata blank.

## Bằng chứng

- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py -q` - **77 passed**.
- Full suite: `uv run pytest -q` - **463 passed, 2 skipped, 1 warning**.
- Static: `uv run python -m compileall -q src tests` và `git diff --check` - **đạt**.

## Trạng thái

Contract offline đã được khóa. Live model-service smoke và production golden
parity vẫn chưa xác minh vì checkout chưa có endpoint, credential và catalog
production thật.
