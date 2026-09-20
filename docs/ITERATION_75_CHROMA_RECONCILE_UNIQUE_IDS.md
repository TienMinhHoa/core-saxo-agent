# Iteration 75 - Chroma reconcile khong chap nhan chunk ID trung

## Pham vi

Iteration nay sieu nho: khoa hop dong `VectorIndex.list_chunk_ids()` de ket qua
tu Chroma khong duoc chua cung mot `chunk_id` nhieu lan. Danh sach trung la dau
hieu index/provider dang khong nhat quan; neu tiep tuc, use case reconcile co
the tinh sai tap stale IDs va tao ket qua xoa/upsert khong on dinh.

## Thay doi

- Them validation fail-closed sau khi da kiem tra danh sach ID la cac chuoi
  khong blank.
- Them regression test TDD voi provider tra ve `['chunk-1', 'chunk-1']`.
- Khong thay doi thu tu ID hop le va khong them provider I/O moi.

## Bang chung kiem chung

- Targeted contract: `uv run pytest tests/test_phase_4_ingestion_contract.py`
  dat.
- Full suite: `uv run pytest` dat.
- Static: `uv run python -m compileall -q src tests` dat.
- Hygiene: `git diff --check` dat.

## Gioi han

Day la kiem chung offline voi fake provider va khong phai production parity hay
live model-service smoke. Live smoke van can endpoint, credential va catalog
production duoc cung cap rieng.
