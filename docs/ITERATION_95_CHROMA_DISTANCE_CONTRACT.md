# Iteration 95 - Chroma distance khong am

## Pham vi

Dong bo hop dong ket qua cua `ChromaVectorIndex` voi `ChromaSemanticRetriever`:
distance do Chroma tra ve phai la so huu han va khong am truoc khi adapter tao
`VectorHit`.

## Thay doi

- Bo sung hai regression case cho distance `-0.1` va `-1`.
- `ChromaVectorIndex` fail-closed voi thong bao ro rang khi provider tra distance am.
- Khong thay doi duong di hop le: distance `0.2` van duoc map thanh `VectorHit`.

## Bang chung kiem thu

- TDD red: 2 test moi fail vi adapter truoc do chi kiem tra finite, chua chan so am.
- Sau implementation: `uv run pytest tests/test_phase_4_ingestion_contract.py tests/test_chroma_semantic_retriever.py -q` -> **117 passed**.
- `uv run python -m compileall -q src tests` -> dat.
- `git diff --check` -> dat.

## Gioi han

Day la xac minh offline. Live model-service smoke va production golden parity
van can endpoint, credential va catalog production duoc phe duyet; iteration
nay khong tu tao gia lap cho cac dieu kien do.
