# Bằng chứng Phase 4 — durable embedding reuse

## Phạm vi iteration 62

Chọn hướng Clean Code: giữ `EmbeddingReuseStore` là port của application và
bổ sung `FileEmbeddingReuseStore` ở infrastructure. Adapter này lưu
`ChunkIndexRecord` bằng JSON, ghi file tạm rồi `os.replace` để tránh file đích
bị ghi dở. File không tồn tại được coi là cache rỗng; payload hỏng bị từ chối
rõ ràng, không fallback im lặng.

## Yêu cầu được đáp ứng

- Cache embedding không còn chỉ sống trong process: tạo instance mới với cùng
  đường dẫn vẫn reuse được vector sau khi instance trước đã lưu.
- Khóa reuse vẫn giữ đúng hợp đồng hiện tại: `chunk_id`, `source_version`,
  `embedding_profile` và `search_text`.
- Dữ liệu được tái dựng qua `ChunkIndexRecord`, nên validation vector,
  provenance và metadata vẫn chạy trước khi được dùng để index.
- Lỗi JSON hoặc schema persisted không bị nuốt; adapter trả lỗi
  `embedding reuse store is corrupt` để workflow không báo indexed giả.

## Bằng chứng kiểm thử

```text
uv run pytest -q tests/test_phase_4_index_document.py
13 passed
```

Test mới chứng minh hai điều: cache sống qua một `FileEmbeddingReuseStore`
instance mới và payload JSON hỏng bị reject. Full suite cần chạy lại ở bước
handoff của iteration kế tiếp; live model service/Chroma vẫn ngoài phạm vi
kiểm thử offline này.
