# Phase 4 - Tái sử dụng embedding cho bản ghi không đổi

## Phạm vi

`IndexDocument` trước đây luôn gọi `EmbeddingProvider` cho mọi lần ingest. Bước
này thêm port `EmbeddingReuseStore` để workflow có thể tìm vector đã tạo cho
cùng `chunk_id`, `source_version`, `embedding_profile` và nguyên văn `search_text`.

Nếu projection nguồn không đổi, provider không bị gọi lại; record vẫn được
upsert vào vector index và report tăng `reused_embedding_count`. Nếu `search_text`
đổi, cache miss và provider được gọi lại. `InMemoryEmbeddingReuseStore` là
adapter bộ nhớ trong, phù hợp cho vòng đời một app process; persistence bền vững
qua restart vẫn là phần việc tiếp theo.

## Bằng chứng kiểm thử

- Test unchanged record xác nhận lần ingest thứ hai không gọi provider và report
  ghi nhận một embedding được tái sử dụng.
- Test source text thay đổi xác nhận provider được gọi lại, không tái sử dụng
  vector cũ.
- Kiểm thử mục tiêu: `uv run pytest -q tests/test_phase_4_index_document.py`
  đạt `11 passed`.

## Ranh giới còn lại

Adapter hiện tại chỉ giữ cache trong process. Chưa claim idempotency qua restart
hoặc live Chroma/model-service; cần một adapter durable thuộc composition root
trước khi đóng tiêu chí đó.
