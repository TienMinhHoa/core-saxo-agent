# Phase 5 – Adapter semantic retrieval Chroma

## Phạm vi iteration 9

Theo lựa chọn Clean Code, iteration này hiện thực lát cắt đầu tiên của
`ChromaSemanticRetriever` trong kế hoạch kiến trúc. Adapter nhận một Chroma
collection và embedding provider đã được composition root tạo sẵn, sau đó map
kết quả SDK thành `ChunkHit` provider-independent. Legacy catalog, FastAPI
route và answer generation chưa bị thay đổi.

## Quy tắc đã thực thi

- `ChunkRetriever.search` vẫn là async; cả embedding blocking và Chroma query
  đều chạy qua `anyio.to_thread.run_sync`.
- `filters` được copy trước khi truyền vào Chroma; `limit < 1` trả về rỗng mà
  không gọi provider.
- Chroma distance được chuyển thành `semantic_score = 1 - distance`, rank được
  đánh số từ 1 và metadata/document được copy vào DTO.
- Không trả object Chroma ra ngoài adapter; `ChunkHit` tự kiểm tra identity,
  rank và score hữu hạn.

## Bằng chứng kiểm thử

```text
`uv run pytest tests/test_chroma_semantic_retriever.py -q` → 2 passed.
`uv run pytest tests/test_phase_5_retrieval_contract.py -q` → 6 passed.
```

Kiểm tra toàn bộ sau khi adapter hoàn tất:

```text
`uv run pytest -q` → 97 passed, 2 skipped, 1 warning.
`uv run python -m compileall -q src tests` → pass.
`git diff --check` → pass.
```

Hai test skip là giới hạn môi trường đã biết: Gradio chưa cài và sample source
không có trong checkout; không phải regression của adapter.
