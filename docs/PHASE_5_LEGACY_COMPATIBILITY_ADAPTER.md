# Adapter tương thích retrieval legacy

## Phạm vi iteration 4

`LegacySemanticRetriever` đưa `music_rag.semantic.semantic_search` qua cùng
`ChunkRetriever` boundary mà retrieval mới đang dùng. Adapter này giữ nguyên
legacy catalog trong giai đoạn strangler migration, nhưng không để route hoặc
use case mới phụ thuộc trực tiếp vào `CatalogStore` hay kiểu `dict` kết quả.

## Contract đã khóa

- Bắt buộc truyền `filters["access_scope"]`; không âm thầm tìm kiếm ngoài
  phạm vi truy cập.
- Từ chối filter legacy chưa được materialize thay vì bỏ qua silently.
- Chạy hàm legacy blocking trong bounded I/O limiter, không khóa event loop.
- Chuẩn hóa mỗi kết quả thành `ChunkHit` với `source_ref` dạng
  `document_id:source_version`, `chunk_ref` là `search_unit_id`, cùng semantic
  và keyword score để presenter/fusion có thể dùng chung boundary.
- Giữ provenance legacy (`evidence_block_ids`, `item_id`, version...) trong
  metadata; không tạo nội dung trả lời mới.

## Bằng chứng kiểm thử

```text
uv run pytest -q tests/test_hybrid_retrieval.py
5 passed
```

Test bao phủ mapping kết quả và provenance, access-scope bắt buộc, filter
không hỗ trợ, cùng các contract RRF/lexical hiện có.

## Giới hạn còn lại

Adapter này chưa chứng minh golden parity production với catalog thật. Việc so
sánh thứ tự/score legacy với semantic hoặc hybrid adapter mới vẫn cần fixture
catalog được chấp thuận và quyết định rõ field nào phải giữ parity trước khi
retire legacy path.
