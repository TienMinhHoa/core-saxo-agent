# Iteration 318 - policy artifact PDF typed

## Muc tieu

Chon huong Clean Code: workflow OCR PDF khong nhan ba callback roi rac cho
`source`, `extraction` va `pages`. `PdfLayoutJobStore` phai so huu policy
cau truc persistence va expose mot DTO typed duy nhat cho workflow.

## Thay doi

- Them `PdfLayoutArtifactPaths` immutable voi ba path artifact can thiet.
- Them `PdfLayoutJobStore.artifact_paths(job_id)` de tao DTO sau khi validate UUID.
- `run_extraction()` nhan `artifact_paths` thay vi ba callback path rieng le.
- HTTP interface chi truyen `JOB_STORE.artifact_paths`; workflow khong con biet
  ten ham hay cau truc thu muc persistence.

## Bang chung

- `tests/test_pdf_layout_job_store.py`: kiem tra DTO typed va cac path canonical.
- `tests/test_phase_7_pdf_layout_wrapper.py`: AST/source contract chan callback
  path cu va yeu cau mot artifact policy duy nhat.
- Targeted: `uv run pytest tests/test_pdf_layout_job_store.py tests/test_phase_7_pdf_layout_wrapper.py -q` -> **27 passed**.
- Full offline: `uv run pytest -q` -> **1012 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests` va `git diff --check` deu thanh cong.

## Gioi han xac minh

Khong co live model-service smoke hoac production golden parity trong checkout
nay vi van thieu endpoint, credential va catalog production duoc phe duyet.

