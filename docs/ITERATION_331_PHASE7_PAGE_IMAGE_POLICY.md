# Iteration 331 - policy duong dan anh trang PDF

## Pham vi

Tach mot policy nho con nam trong HTTP interface: validate `page_number` va
tao duong dan `pages/page-N.png`. Theo Clean Code, `PdfLayoutJobStore` la
boundary so huu artifact filesystem; route chi dieu phoi va tra `FileResponse`.

## Thay doi

- Them `PdfLayoutJobStore.page_image_path(job_id, page_number)`.
- Store tu choi so trang khong phai so nguyen duong, bao gom `bool`, float va
  chuoi; UUID van duoc validate qua `artifact_paths()`.
- Route `GET /api/jobs/{job_id}/pages/{page_number}` khong con tu ghep ten file,
  ma dung policy cua job store va map input khong hop le thanh HTTP 404.
- Them contract test de ngan viec business logic path quay lai HTTP interface.

## Bang chung

- Targeted: `48 passed` cho job store va PDF Phase 7 contracts.
- Full offline: `1035 passed, 18 skipped, 1 warning`.
- `uv run python -m compileall -q src tests`: dat.
- `git diff --check`: dat; chi con canh bao LF/CRLF tu Git.
- Live model-service smoke va production parity chua xac minh vi checkout van
  thieu endpoint, credential va production catalog.

## Ket luan

Slice Phase 7 nay da chuyen them mot policy filesystem khoi route vao
persistence boundary, khong thay doi format API thanh cong hien co.
