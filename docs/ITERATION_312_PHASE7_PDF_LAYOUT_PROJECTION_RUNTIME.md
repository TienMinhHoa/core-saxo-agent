# Iteration 312 - sua loi runtime projection trang thai PDF

## Pham vi

Tiep tuc Phase 7 cua `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` bang mot slice
nho: bao dam route layout su dung cung policy public-state cua
`PdfLayoutJobStore` sau khi helper `_public_state()` da duoc loai bo khoi HTTP
interface.

## Thay doi

- Sua `job_layout()` de goi `JOB_STORE.public_state(state)` thay vi tham chieu
  helper da xoa.
- Them regression test runtime voi job store gia lap, bao dam route tra ve
  public state va danh sach layout ma khong lam lo truong noi bo.

## Bang chung

- Test truoc khi sua that bai voi `NameError: name '_public_state' is not defined`.
- Targeted: `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py -q` dat **10 passed**.
- Full suite: `uv run pytest --basetemp=.pytest-tmp-312-final -q` dat **1001
  passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests`: dat.
- `git diff --check`: dat; Git chi canh bao chuan hoa LF/CRLF tren Windows.

## Gioi han xac minh

Live model-service smoke va production parity van chua chay vi checkout thieu
endpoint, credential va production catalog. Khong khoi dong background process.
