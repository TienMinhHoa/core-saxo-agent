# Iteration 82 - Contract metadata reserved cua Chroma

## Pham vi

Bao ve cac truong metadata he thong ma `ChromaVectorIndex` luon tu bo sung
(`document_ref`, `source_version`, `embedding_profile`, `access_scope`). Metadata
tu `ChunkIndexRecord` khong duoc phep dung cung key de tranh viec adapter ghi de
am tham gia tri provenance va access-scope.

## Thay doi

- Them regression test TDD cho ca bon reserved key.
- Adapter fail-closed truoc provider I/O voi `ValueError` neu metadata chua
  reserved key.

## Bang chung kiem thu

- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py -q` -> **62 passed**.
- Full suite: `uv run pytest -q` -> **448 passed, 2 skipped, 1 warning**.
- `python -m compileall -q src tests` thanh cong.
- `git diff --check` thanh cong.
- Live Chroma/model-service smoke chua chay vi checkout van thieu endpoint,
  credential va production catalog duoc cap quyen.
