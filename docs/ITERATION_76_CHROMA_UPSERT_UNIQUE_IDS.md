# Iteration 76 - Khoa ID trung trong batch upsert Chroma

## Pham vi

Iteration nay khoa mot loi nho tai boundary `ChromaVectorIndex`: mot batch
`upsert_chunks` khong duoc chua cung `chunk_id` nhieu lan. Neu gui batch trung
ID xuong provider, ket qua ghi co the khong xac dinh va lam sai trang thai
reconcile.

## Thay doi

- Them validation uniqueness truoc moi provider I/O trong `upsert_chunks`.
- Them regression test TDD voi cung mot `ChunkIndexRecord` xuat hien hai lan.
- Khong thay doi thu tu hoac cach xu ly batch hop le.

## Bang chung kiem chung

- Targeted contract: `uv run pytest tests/test_phase_4_ingestion_contract.py` dat.
- Full suite: `uv run pytest` dat.
- Static: `uv run python -m compileall -q src tests` dat.
- Hygiene: `git diff --check` dat.

## Gioi han

Day la kiem chung offline voi fake provider, khong phai production parity hay
live model-service smoke. Live smoke van can endpoint, credential va catalog
production duoc cung cap rieng.
