# Iteration 69 - Contract query vector Chroma fail-closed

## Pham vi

Siet boundary `ChromaVectorIndex.search` theo hop dong adapter Chroma trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: query vector phai duoc kiem tra
truoc khi goi provider blocking.

## Thay doi

- Tu choi query vector rong, chuoi/bytes, boolean, so khong finite hoac gia tri
  khong phai so.
- Kiem tra dimension cua query vector voi dimension cau hinh cua collection;
  loi xay ra truoc Chroma I/O.
- Chuan hoa vector hop le thanh `list[float]` de payload vao Chroma co kieu
  on dinh.
- Bo sung 5 regression cases cho malformed vector va sai dimension.

## Bang chung kiem chung

- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py -q` - 35 passed.
- Full suite: `uv run pytest -q` - 413 passed, 2 skipped, 1 warning.
- `python -m compileall -q src tests` - dat.
- `git diff --check` - dat; Git chi canh bao line ending CRLF.

## Trang thai con lai

Live model-service smoke va production golden parity van chua xac minh vi
checkout thieu endpoint, credential va catalog production thuc te.
