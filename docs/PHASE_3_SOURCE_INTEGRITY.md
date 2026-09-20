# Phase 3 - Kiem tra toan ven source artifact

## Pham vi iteration 28

`ProcessDocument` doi chieu ca kich thuoc va SHA-256 cua payload doc tu
`ArtifactRepository` voi `ArtifactRef` truoc khi goi `PdfExtractor`.

Neu bytes bi thay doi sau khi ghi, du kich thuoc khong doi, workflow nem
`ValueError` va khong goi extractor. Dieu nay ngan payload bi tamper vuot qua
boundary extraction.

## Bang chung

- Them contract test cho payload cung kich thuoc nhung sai checksum.
- Test xac nhan extractor khong bi goi khi source khong toan ven.
- `uv run pytest tests/test_phase_3_process_document.py -q --basetemp=.pytest-tmp`:
  4 passed.
- `uv run pytest -q --basetemp=.pytest-tmp`: 146 passed, 2 skipped, 1 warning.
- `python -m compileall -q src` va `git diff --check`: dat.
- Cac gioi han van con: chua co upload endpoint, chua persist output extraction,
  va chua co ingestion/index wiring.
