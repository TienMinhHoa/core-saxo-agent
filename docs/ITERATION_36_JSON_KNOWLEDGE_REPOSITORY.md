# Iteration 36 - JSON knowledge repository adapter

## Pham vi

Bo sung adapter production nho cho `KnowledgeRepository`: luu moi
`KnowledgeChunk` thanh mot sidecar JSON trong thu muc backend-owned. Adapter nay
khong luu bytes artifact va khong phu thuoc Chroma, dung voi phan Metadata/
knowledge repository trong ke hoach kien truc.

## Thay doi

- Them `JsonKnowledgeRepository` tai `src/saxophone/platform/knowledge.py`.
- Upsert dung JSON atomic (`flush`, `fsync`, `os.replace`) va chay qua bounded
  blocking-I/O limiter de khong chan event loop.
- Doc sidecar kiem tra JSON object, chuan hoa cac list metadata thanh tuple,
  sau do tao lai `KnowledgeChunk` de domain validation duoc ap dung.
- File duoc dat theo SHA-256 cua `chunk_id`, nen chunk ID khong bao gio tro
  thanh local filesystem path.
- Them 4 contract tests: round-trip va replace, missing record, tamper identity,
  va khong de lai file tam.

## Bang chung xac minh

```text
uv run pytest tests/test_phase_2_json_knowledge_repository.py -q
4 passed

uv run pytest -q
332 passed, 2 skipped, 1 warning

uv run python -m compileall -q src tests
git diff --check
```

Hai test skip van la Gradio khong cai va sample source khong co trong checkout;
khong lien quan thay doi iteration nay. Ruff khong co trong moi truong hien tai.

## Gioi han con lai

Adapter da ton tai nhung chua duoc noi vao ingestion workflow production; viec
chon schema document status va composition wiring la mot slice rieng. Live
model-service smoke va production retrieval parity van bi chan boi endpoint,
credential va catalog production chua duoc cung cap.
