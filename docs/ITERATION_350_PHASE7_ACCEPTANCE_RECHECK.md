# Iteration 350 - kiem tra lai acceptance Phase 7

## Pham vi

Kiem tra lai don vi nho nhat con lai cua Phase 7: entrypoint web duy nhat,
ranh gioi compatibility wrapper, dependency enforcement va kha nang dong goi
backend. Khong thay doi notes cua GNHF.

## Bang chung

- `uv run pytest tests/test_phase_7_dependency_enforcement.py
  tests/test_phase_7_backend_entrypoint.py tests/test_phase_7_legacy_ui_boundary.py
  tests/test_phase_7_pdf_layout_wrapper.py -q`: **96 passed**.
- `uv run pytest -q`: **1065 passed, 18 skipped, 1 warning** trong 41.11 giay.
- `python -m compileall -q src tests`: dat.
- `git diff --check`: dat.

## Ket luan

Phase 7 van dat o muc offline: `saxophone-api` la backend web chinh; `app.py`
va `src/pdf_layout_web.py` chi con compatibility wrapper; package metadata
khong quang ba lai package OCR legacy; cac test dependency ngan route/use case
phu thuoc truc tiep vao provider SDK hoac legacy implementation.

18 test skip la co chu y do Gradio/sample source/symbolic-link privilege cua
moi truong Windows. Live model-service smoke va production parity chua the
xac minh vi checkout khong co endpoint, credential va production catalog.

## Buoc tiep theo

Neu co endpoint, credential va catalog production duoc cap, chay live smoke
theo runbook va ghi ket qua rieng. Khong xoa compatibility wrapper cho den khi
feature parity va migration decision duoc phe duyet.
