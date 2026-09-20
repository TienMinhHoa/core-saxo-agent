# Phase 4 - Ranh giới embedding của `IndexDocument`

## Phạm vi iteration 36

Use case `IndexDocument` nay da goi port `EmbeddingProvider` truoc khi ghi du lieu
vao `VectorIndex`. Application layer khong biet SDK model hay Chroma.

## Thay doi

- Nhan `EmbeddingProvider` qua constructor de dependency inversion ro rang.
- Gui cap `(chunk_id, search_text)` cung `source_version` den provider.
- Kiem tra so luong embedding, chunk ID, source version va model profile truoc khi
  tao ban ghi index moi.
- Chi upsert cac `ChunkIndexRecord` da duoc thay embedding bang vector tu provider.
- Loi embedding hoac vector index deu tra `IngestionReport(indexed=False)`; khong
  danh dau thanh cong im lang va khong goi index neu embedding khong hop le.

## Bang chung kiem thu

- `uv run pytest tests/test_phase_4_index_document.py -q`: 9 passed.
- Cac test bao phu happy path, loi embedding, loi vector index, record sai scope
  va embedding sai chunk ID/source version/model profile.

## Gioi han con lai

Iteration nay chua noi `IndexDocument` vao route upload hoac workflow extraction.
Composition root da tao `EmbeddingProvider`, nhung ingestion van chua duoc danh dau
ready cho den khi co `VectorIndex` va orchestration persist end-to-end.
