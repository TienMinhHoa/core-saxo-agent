# Iteration 325 - ranh gioi ghi upload PDF

## Pham vi

Tiep tuc Phase 7 cua `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: route HTTP
khong tu chon va ghi file PDF vao filesystem. Chinh sach artifact source PDF
duoc dat tai `PdfLayoutJobStore`.

## Thay doi

- Them `PdfLayoutJobStore.save_uploaded_pdf()` de validate gioi han byte,
  ghi vao `source.pdf`, tra ve so byte va xoa file partial neu ghi that bai.
- Route upload chi dieu phoi qua store va chay thao tac ghi blocking bang
  `asyncio.to_thread`, sau do dong `UploadFile` trong `finally`.
- Giu cleanup job qua `discard_job()` neu upload rong, qua lon hoac loi I/O.
- Cap nhat contract test de khong cho route truy cap truc tiep
  `artifact_paths(job_id).source_pdf`.

## Bang chung

- `uv run pytest -q tests/test_pdf_layout_job_store.py tests/test_phase_7_pdf_layout_wrapper.py --basetemp=.pytest-tmp`
  dat **35 passed**.
- Full suite, `compileall` va `git diff --check` duoc chay sau thay doi.
- Chua chay live model-service smoke vi checkout van thieu endpoint,
  credential va production catalog; day la blocker moi truong, khong phai
  ket qua cua slice nay.

## Gioi han con lai

Helper `_save_upload` legacy van con trong module interface nhung khong con
duoc route goi; mot slice cleanup rieng can loai bo no an toan.
