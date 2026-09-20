# Iteration 83 - Chroma search khong chap nhan chunk ID trung

## Pham vi

Dong bo contract ID cua ket qua search voi reconcile, upsert va delete. Moi
`chunk_id` trong mot ket qua Chroma phai la chuoi khong rong va duy nhat; neu
provider tra ve ID trung, adapter phai fail-closed truoc khi tao `VectorHit`.

## Thay doi

- Them regression test TDD cho ket qua search co hai row cung `chunk_id`.
- Bo sung kiem tra uniqueness trong `_validated_chroma_rows`.
- Provider response sai khong duoc am tham duoc map thanh hai hit cung danh tinh.

## Bang chung kiem thu

- Test truoc thay doi that bai: test moi khong nhan duoc `ValueError`.
- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py -q` -> **63 passed**.
- Full suite: `uv run pytest -q` -> **449 passed, 2 skipped, 1 warning**.
- `python -m compileall -q src tests` thanh cong.
- `git diff --check` thanh cong.
- Live Chroma/model-service smoke chua chay vi checkout van thieu endpoint,
  credential va production catalog duoc cap quyen.
