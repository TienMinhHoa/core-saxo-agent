# Iteration 78 - Kiem soat limit cua Chroma search

## Pham vi

Iteration nay bo sung contract fail-closed cho `ChromaVectorIndex.search`:
`limit` phai la so nguyen khong am va khong duoc la `bool`, so thap phan hoac
chuoi. Hanh vi hop le `limit=0` van tra danh sach rong ma khong goi provider.

## Thay doi

- Them validation `limit` truoc moi provider I/O.
- Truyen gia tri da validate vao `n_results` cua Chroma.
- Them 4 regression test TDD cho so am, bool, so thap phan va chuoi.
- Khong thay doi ket qua cua search voi limit hop le.

## Bang chung kiem chung

- Targeted contract: `uv run pytest tests/test_phase_4_ingestion_contract.py` dat,
  **46 passed**.
- Static: `uv run python -m compileall -q src tests` dat.
- Hygiene: `git diff --check` dat.
- Full suite: `uv run pytest` dat, **432 passed, 2 skipped, 1 warning**.

## Gioi han

Day la kiem chung offline voi fake provider, khong phai production parity hay
live model-service smoke. Live smoke van can endpoint, credential va catalog
production duoc cung cap rieng.
