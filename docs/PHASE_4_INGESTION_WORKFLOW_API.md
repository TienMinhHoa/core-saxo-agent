# Bằng chứng Phase 4 — workflow ingestion qua composition root và API

## Phạm vi lát cắt

Lát cắt này nối `IndexDocument` đã có với composition root và inbound FastAPI
adapter. API không biết Chroma hay model client; nó chỉ nhận DTO, gọi use case
và trả `IngestionReport`. `VectorIndex` vẫn là port để adapter hạ tầng có thể
được thay bằng fake trong test hoặc Chroma adapter ở runtime.

## Thay đổi đã thực hiện

- `AppOverrides.vector_index` cho phép inject vector index; factory tự compose
  `IndexDocument` cùng `EmbeddingProvider`.
- Thêm `POST /api/v1/documents/{document_ref}/ingest` với request typed gồm
  profile, access scope và các chunk đầu vào.
- Route chuyển chunk thành `ChunkIndexRecord`, giữ document/source/profile/scope
  nhất quán rồi gọi `IndexDocument`.
- Health báo `ingestion=ready` chỉ khi workflow đã được compose; nếu chưa có
  vector index, route trả `503` rõ ràng thay vì giả vờ ingestion hoạt động.
- Response công khai các counter/trạng thái của `IngestionReport`, không lộ
  provider internals.

## Bằng chứng kiểm thử

Đã chạy tại repository root:

```text
uv run pytest tests/test_phase_7_api_routes.py -q
9 passed, 1 warning

uv run pytest -q
170 passed, 2 skipped, 1 warning

python -m compileall -q src
git diff --check
```

Hai test skip là fixture môi trường cũ: Gradio chưa cài và sample source không
có trong checkout; không liên quan đến workflow ingestion mới.

## Giới hạn còn lại

Route hiện nhận các chunk đã chuẩn hóa để chứng minh đường đi
API → `IndexDocument` → embedding provider → vector index. Việc đọc extraction
manifest, chunk/paragraph deterministic, tagging và persistence knowledge
repository thành một pipeline tự động vẫn là lát cắt kế tiếp. Chưa claim live
model service hoặc Chroma server từ kiểm thử offline này.
