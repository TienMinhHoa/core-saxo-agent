# Remote embedding provider - Phase 4

## Phạm vi iteration 34

Lát cắt này bổ sung `EmbeddingProvider` và adapter
`RemoteEmbeddingProvider`. Ingestion chỉ biết port; adapter dùng
`ModelClient` chung để gọi external model service với `ModelTask.EMBED`, không
khởi tạo SDK model, CUDA hoặc Paddle trong backend.

## Hợp đồng đã khóa

- Input là danh sách `(chunk_id, text)` cùng `source_version`.
- Request gửi `source_version` trong metadata và yêu cầu schema `embedding-v1`.
- Response phải có đúng task, schema, source version và danh sách embedding theo
  đúng thứ tự chunk đã gửi.
- Mỗi vector được map thành `EmbeddingRecord` immutable; thiếu vector, sai shape
  hoặc lệch chunk ID bị từ chối trước khi caller nhận dữ liệu.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_4_remote_embedding_provider.py -q
3 passed

uv run pytest -q
162 passed, 2 skipped, 1 warning
```

Test bao phủ mapping thành công, output thiếu vector và response có chunk thừa.
Chưa có live model-service smoke hoặc composition-root wiring cho ingestion; đó
là lát cắt tiếp theo.
