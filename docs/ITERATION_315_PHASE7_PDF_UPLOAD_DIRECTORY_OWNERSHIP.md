# Iteration 315 - ranh gioi so huu thu muc upload PDF

## Pham vi

Sua mot loi boundary nho trong route `POST /api/jobs`: route khong tu tao
thu muc job nua. `PdfLayoutJobStore.create_uploaded_job()` tao thu muc va
state ban dau mot lan duy nhat, sau do route chi ghi file upload vao thu muc
da duoc store tao.

## Bang chung

- Them regression contract: `test_pdf_upload_route_delegates_initial_state_creation_to_job_store`
  cam route goi `job_dir.mkdir(...)`.
- Route tao state qua `JOB_STORE.create_uploaded_job()` truoc khi ghi
  `source.pdf`, tranh xung dot voi `exist_ok=False` trong store.
- Neu upload loi hoac file rong, cleanup van xoa dung job directory da duoc
  tao trong request hien tai.

## Kiem tra

- Targeted: `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py tests/test_pdf_layout_job_store.py`
- Full suite: `uv run pytest` dat **1007 passed, 18 skipped, 1 warning**.
- Static: `python -m compileall -q src tests` va `git diff --check` dat.

Live model-service smoke va production parity chua duoc chay do checkout van
thieu endpoint, credential va production catalog that.
