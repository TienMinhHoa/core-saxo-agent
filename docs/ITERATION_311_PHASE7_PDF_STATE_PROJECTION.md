# Iteration 311 - tach policy projection trang thai PDF khoi HTTP interface

## Pham vi

Tiep tuc Phase 7 cua `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` bang mot slice
nho: interface HTTP khong tu dinh nghia lai danh sach truong state cong khai.
Policy nay thuoc ve `PdfLayoutJobStore`, noi dang so huu persistence va public
state projection.

## Thay doi

- Xoa helper `_public_state()` khoi `src/saxophone/interfaces/pdf_layout_web.py`.
- Cac route tao job, bat dau extraction va doc status deu goi
  `JOB_STORE.public_state(...)`.
- Them contract test ngan chan policy projection quay lai interface.

## Bang chung

- Targeted: `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py tests/test_pdf_layout_job_store.py`
  dat **15 passed**.
- Full suite: `uv run pytest --basetemp=.pytest-tmp-311-full` dat **1000 passed,
  18 skipped, 1 warning**.
- `python -m compileall -q src tests`: dat.
- `git diff --check`: dat; Git chi canh bao chuan hoa LF/CRLF tren Windows.

## Gioi han xac minh

Live model-service smoke va production parity van chua chay vi checkout thieu
endpoint, credential va production catalog. Khong khoi dong background process.
