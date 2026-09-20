# Bằng chứng Phase 4 — wiring durable embedding reuse trong composition root

## Phạm vi

Lát cắt này hoàn tất phần còn thiếu sau `PHASE_4_DURABLE_EMBEDDING_REUSE`: composition root mặc định tạo `FileEmbeddingReuseStore` dưới `SAXO_DATA_ROOT/embedding-reuse.json`. Khi vector index được bật, `IndexDocument` dùng cùng store durable đó thay vì cache in-memory.

## Thay đổi

- `FileEmbeddingReuseStore` công khai thuộc tính `path` để composition/test có thể kiểm tra wiring mà không chạm vào state private.
- `create_app()` tạo durable reuse store mặc định cho mọi app instance.
- `AppOverrides.embedding_reuse` vẫn được ưu tiên để test hoặc triển khai có adapter khác.
- Khi `vector_index` được cung cấp nhưng chưa có `index_document` override, use case `IndexDocument` nhận chính store durable đã compose.

## Bằng chứng kiểm thử

Đã chạy:

```text
uv run pytest tests/test_phase_1_composition_root.py -q
16 passed, 1 warning
```

Các contract mới kiểm tra:

1. Composition mặc định tạo đúng `FileEmbeddingReuseStore` tại `data_root/embedding-reuse.json`.
2. Composition có indexing dùng durable store mặc định, không quay lại `InMemoryEmbeddingReuseStore`.

## Giới hạn còn lại

Adapter hiện vẫn được thiết kế cho single-process; khóa đồng thời giữa nhiều process và live smoke với model/Chroma chưa nằm trong lát cắt này.
