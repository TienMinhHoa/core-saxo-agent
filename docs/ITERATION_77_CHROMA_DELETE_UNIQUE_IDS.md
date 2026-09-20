# Iteration 77 - Khoa ID trung trong batch delete Chroma

## Pham vi

Iteration nay bo sung contract fail-closed cho `ChromaVectorIndex.delete_chunks`:
mot batch xoa khong duoc chua cung `chunk_id` nhieu lan. Dieu nay dong bo voi
reconcile va upsert, dong thoi tranh gui yeu cau xoa mo ho xuong provider.

## Thay doi

- Them validation uniqueness truoc moi provider I/O trong `delete_chunks`.
- Them regression test TDD voi hai ID trung va provider khong duoc goi.
- Khong thay doi xu ly batch hop le hoac batch rong.

## Bang chung kiem chung

- Targeted contract: `uv run pytest tests/test_phase_4_ingestion_contract.py` dat, **42 passed**.
- Full suite: `uv run pytest` dat, **428 passed, 2 skipped, 1 warning**.
- Static: `uv run python -m compileall -q src tests` dat.
- Hygiene: `git diff --check` dat.

## Gioi han

Day la kiem chung offline voi fake provider, khong phai production parity hay
live model-service smoke. Live smoke van can endpoint, credential va catalog
production duoc cung cap rieng.
